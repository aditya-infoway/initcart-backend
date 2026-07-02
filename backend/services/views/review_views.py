from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.contrib.contenttypes.models import ContentType
from django.db.models import Avg
from services.models.review import ServiceReview
from services.serializers.review_serializers import ServiceReviewSerializer
from services.models.real_estate import Property


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
            except OrderItem.DoesNotExist:
                return Response(
                    {"error": "Invalid order item for this product"}, status=400
                )

            if order_item.order.order_status != "delivered" and order_item.item_status != "delivered":
                return Response(
                    {"error": "You can only review products after delivery"},
                    status=403,
                )

        # ✅ Duplicate check is scoped to (user, object, order_item) — NOT just object_id
        if ServiceReview.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=object_id,
            order_item=order_item,
        ).exists():
            return Response({"error": "You have already reviewed this order"}, status=400)

        serializer = ServiceReviewSerializer(data=request.data)

        if serializer.is_valid():
            serializer.save(
                user=request.user,
                content_type=content_type,
                object_id=object_id,
                order_item=order_item,   # ✅ THIS LINE is the critical fix — must be saved
            )
            return Response({"success": True, "data": serializer.data})

        return Response({"success": False, "errors": serializer.errors}, status=400)


class ReviewableOrderItemsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        product_id = request.query_params.get("product_id")

        from ecommerce.models.order import OrderItem

        qs = OrderItem.objects.filter(
            order__customer=request.user,
            order__order_status="delivered",
        ).select_related("order", "product")

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
                "delivered_at": item.order.updated_at,
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
    permission_classes = [AllowAny]

    def get(self, request):
        model_name = request.query_params.get("model")
        object_id = request.query_params.get("object_id")
        order_item_id = request.query_params.get("order_item_id")  # ✅ scoping param

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

        has_reviewed = False
        if request.user.is_authenticated:
            review_filter = {"user": request.user}
            if order_item_id:
                review_filter["order_item_id"] = order_item_id
            has_reviewed = reviews.filter(**review_filter).exists()

        serializer = ServiceReviewSerializer(reviews, many=True)

        return Response({
            "success": True,
            "has_reviewed": has_reviewed,
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