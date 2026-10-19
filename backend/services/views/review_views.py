from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg, Q
from services.models.review import ServiceReview
from services.serializers.review_serializers import ServiceReviewSerializer
from services.models.real_estate import Property


# ─────────────────────────────────────────────────────────────────────────────
# ✅ PER-ITEM REVIEW RULE (single source of truth)
# Review ek poore order ka nahi, har OrderItem ka alag hota hai.
# Jis item ka item_status 'delivered' ho gaya, bas usi item ka review khulega
# — chahe order ka status abhi 'pending' / 'shipped' ho (multi-vendor orders).
# Fallback: purane orders jahan order 'delivered' hai lekin item_status update
# nahi hua, wahan bhi allow (cancelled / refunded item ko chhodkar).
# ─────────────────────────────────────────────────────────────────────────────
def is_item_reviewable(order_item):
    if order_item.item_status == "delivered":
        return True
    return (
        order_item.order.order_status == "delivered"
        and order_item.item_status not in ("cancelled", "refunded")
    )


class AddServiceReview(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        model_name = request.data.get("model")
        object_id = request.data.get("object_id")
        order_item_id = request.data.get("order_item_id")  # ✅ REQUIRED for products

        if not model_name or not object_id:
            return Response({"error": "Model and object_id are required"}, status=400)

        try:
            content_type = ContentType.objects.get(model=model_name.lower())
        except ContentType.DoesNotExist:
            return Response({"error": "Invalid service type"}, status=400)

        order_item = None

        if model_name.lower() == "product":
            if not order_item_id:
                return Response(
                    {"error": "order_item_id is required to review a product"},
                    status=400,
                )

            from ecommerce.models.order import OrderItem

            try:
                order_item = OrderItem.objects.select_related("order").get(
                    id=order_item_id,
                    order__customer=request.user,
                    product_id=object_id,
                )
            except (OrderItem.DoesNotExist, ValueError):
                return Response(
                    {"error": "Invalid order item for this product"}, status=400
                )

            # ✅ Per-item delivery check
            if not is_item_reviewable(order_item):
                return Response(
                    {"error": "You can only review this item after it is delivered"},
                    status=403,
                )

        # ✅ Duplicate check is scoped to (user, object, order_item)
        if ServiceReview.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=object_id,
            order_item=order_item,
        ).exists():
            return Response({"error": "You have already reviewed this item"}, status=400)

        serializer = ServiceReviewSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(
                user=request.user,
                content_type=content_type,
                object_id=object_id,
                order_item=order_item,
            )
            return Response({"success": True, "data": serializer.data})

        return Response({"success": False, "errors": serializer.errors}, status=400)


class ReviewableOrderItemsAPIView(APIView):
    """
    ✅ Ab order ka status nahi, har ITEM ka status dekha jata hai.
    Order pending ho lekin ek item delivered ho to wo item yahan aayega.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        product_id = request.query_params.get("product_id")

        from ecommerce.models.order import OrderItem

        qs = (
            OrderItem.objects.filter(order__customer=request.user)
            .filter(
                Q(item_status="delivered")
                | (
                    Q(order__order_status="delivered")
                    & ~Q(item_status__in=["cancelled", "refunded"])
                )
            )
            .select_related("order", "product")
        )

        if product_id:
            qs = qs.filter(product_id=product_id)

        content_type = ContentType.objects.get(model="product")

        reviewed_order_item_ids = set(
            ServiceReview.objects.filter(
                user=request.user,
                content_type=content_type,
                order_item__in=qs,
            ).values_list("order_item_id", flat=True)
        )

        data = [
            {
                "order_item_id": item.id,
                "order_id": item.order_id,
                "order_number": item.order.order_number,
                "product_id": item.product_id,
                "product_name": item.product_name,
                "item_status": item.item_status,
                # item ki apni delivery date; purane data ke liye order wali
                "delivered_at": item.delivered_at or item.order.delivered_at or item.order.updated_at,
                "already_reviewed": item.id in reviewed_order_item_ids,
            }
            for item in qs.order_by("-order__created_at")
        ]

        return Response({"success": True, "data": data})


class ServiceReviewListAPIView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        model_name = request.GET.get("model")
        object_id = request.GET.get("object_id")

        if not model_name or not object_id:
            return Response({"error": "model and object_id required"}, status=400)

        try:
            content_type = ContentType.objects.get(model=model_name.lower())
        except ContentType.DoesNotExist:
            return Response({"error": "Invalid service type"}, status=400)

        reviews = ServiceReview.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).select_related("user").order_by("-created_at")

        serializer = ServiceReviewSerializer(reviews, many=True)

        avg_rating = (
            reviews.aggregate(avg=Avg("rating"))["avg"] or 0
        )

        return Response({
            "total_reviews": reviews.count(),
            "average_rating": round(avg_rating, 1),
            "reviews": serializer.data
        })


class ServiceReviewList(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        model_name = request.query_params.get("model")
        object_id = request.query_params.get("object_id")

        if not model_name or not object_id:
            return Response({"error": "Model and object_id are required"}, status=400)

        try:
            content_type = ContentType.objects.get(model=model_name.lower())
        except ContentType.DoesNotExist:
            return Response({"error": "Invalid service type"}, status=400)

        reviews = ServiceReview.objects.filter(
            content_type=content_type,
            object_id=object_id
        )

        serializer = ServiceReviewSerializer(reviews, many=True)
        return Response({"success": True, "data": serializer.data})


class SearchServiceReviewList(APIView):
    """
    ✅ PER-ITEM review status.

    Query params:
      model, object_id          -> required (e.g. model=product&object_id=5)
      order_item_id (optional)  -> us specific order item ka status chahiye

    Response me naya:
      has_reviewed  -> is ORDER ITEM ka review ho chuka? (order_item_id ho to
                       sirf usi item ke liye, warna user ne kabhi bhi review kiya ho)
      can_review    -> True sirf jab: item user ka hai + product match + item
                       delivered hai + is item ka review abhi nahi hua
      item_status   -> us item ka status (frontend ke liye)
      my_review     -> is item par user ka diya review (agar hai)
    """
    permission_classes = [AllowAny]

    def get(self, request):
        model_name = request.query_params.get("model")
        object_id = request.query_params.get("object_id")
        order_item_id = request.query_params.get("order_item_id")

        if not model_name or not object_id:
            return Response({"error": "Model and object_id are required"}, status=400)

        try:
            content_type = ContentType.objects.get(model=model_name.lower())
        except ContentType.DoesNotExist:
            return Response({"error": "Invalid service type"}, status=400)

        if order_item_id:
            try:
                order_item_id = int(order_item_id)
            except (TypeError, ValueError):
                return Response({"error": "order_item_id must be a number"}, status=400)

        reviews = ServiceReview.objects.filter(
            content_type=content_type,
            object_id=object_id
        )

        has_reviewed = False
        can_review = False
        item_status = None
        my_review = None

        if request.user.is_authenticated:
            review_filter = {"user": request.user}
            if order_item_id:
                review_filter["order_item_id"] = order_item_id
            user_reviews = reviews.filter(**review_filter)
            has_reviewed = user_reviews.exists()

            if has_reviewed:
                my_review = ServiceReviewSerializer(user_reviews.first()).data

            # ✅ Per-item eligibility (sirf product + order_item_id ke liye)
            if model_name.lower() == "product" and order_item_id:
                from ecommerce.models.order import OrderItem

                order_item = (
                    OrderItem.objects.select_related("order")
                    .filter(
                        id=order_item_id,
                        order__customer=request.user,
                        product_id=object_id,
                    )
                    .first()
                )
                if order_item:
                    item_status = order_item.item_status
                    can_review = is_item_reviewable(order_item) and not has_reviewed

        serializer = ServiceReviewSerializer(reviews, many=True)

        return Response({
            "success": True,
            "has_reviewed": has_reviewed,
            "can_review": can_review,
            "item_status": item_status,
            "my_review": my_review,
            "data": serializer.data
        })


class RealEstateReviewAPIView(APIView):
    """
    Dedicated Review API for Property (Real Estate)
    """

    def post(self, request):
        if not request.user.is_authenticated:
            return Response({"error": "Authentication required"}, status=401)

        object_id = request.data.get("object_id")

        if not object_id:
            return Response({"error": "object_id is required"}, status=400)

        content_type = ContentType.objects.get_for_model(Property)

        if ServiceReview.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=object_id,
            order_item=None,
        ).exists():
            return Response({"error": "Already reviewed"}, status=400)

        serializer = ServiceReviewSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(
                user=request.user,
                content_type=content_type,
                object_id=object_id,
            )
            return Response({"success": True, "data": serializer.data})

        return Response({"success": False, "errors": serializer.errors}, status=400)

    def get(self, request):
        object_id = request.query_params.get("object_id")

        if not object_id:
            return Response({"error": "object_id is required"}, status=400)

        content_type = ContentType.objects.get_for_model(Property)

        reviews = ServiceReview.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).select_related("user").order_by("-created_at")

        serializer = ServiceReviewSerializer(reviews, many=True)

        avg_rating = reviews.aggregate(avg=Avg("rating"))["avg"] or 0

        return Response({
            "total_reviews": reviews.count(),
            "average_rating": round(avg_rating, 1),
            "reviews": serializer.data
        })