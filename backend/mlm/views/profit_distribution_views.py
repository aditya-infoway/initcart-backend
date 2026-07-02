#mlm/views/profit_distribution_views.py
from users.utils.permissions import IsSuperAdmin
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from mlm.models.profit_distribution import ProfitDistribution
from mlm.serializers.profit_distribution_serializer import ProfitDistributionSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.generics import RetrieveUpdateDestroyAPIView


class ProfitDistributionCreateAPIView(APIView):

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def post(self, request):

        # Prevent multiple records
        if ProfitDistribution.objects.exists():
            return Response(
                {"error": "Profit distribution already exists. Please update it."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ProfitDistributionSerializer(data=request.data)

        if serializer.is_valid():
            obj = serializer.save() 

            return Response({
                "message": "Profit distribution created",
                "data": serializer.data
            })

        return Response(serializer.errors, status=400)

class ProfitDistributionAPIView(APIView):

    def get(self, request):

        obj = ProfitDistribution.objects.first()

        if not obj:
            return Response({"message": "Distribution not set yet"})

        serializer = ProfitDistributionSerializer(obj)

        return Response(serializer.data)

class ProfitDistributionUpdateAPIView(APIView):

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def put(self, request):

        try:
            obj = ProfitDistribution.objects.first()
        except ProfitDistribution.DoesNotExist:
            return Response({"error": "Distribution not found"}, status=404)

        serializer = ProfitDistributionSerializer(obj, data=request.data)

        if serializer.is_valid():
            serializer.save()

            return Response({
                "message": "Profit distribution updated",
                "data": serializer.data
            })

        return Response(serializer.errors, status=400)


class ProfitDistributionDeleteAPIView(APIView):

    authentication_classes = [JWTAuthentication, SessionAuthentication]
    permission_classes = [IsSuperAdmin]

    def delete(self, request, pk):

        try:
            obj = ProfitDistribution.objects.get(pk=pk)
        except ProfitDistribution.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        obj.delete()

        return Response({
            "message": "Profit distribution deleted"
        })    
        
        