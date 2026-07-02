from django.utils import timezone 
from ecommerce.models.campaign import Campaign , CampaignProduct
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from ecommerce.models.vendor import Vendor
from django.contrib.auth import get_user_model
from services.models.banners import (
    GymBigAd, GymSmallAd, ProfessionalBigAd, ProfessionalSmallAd, 
    SaloonBigAd, SaloonSmallAd, 
    TravelAgencySmallAd, TravelAgencyBigAd,
    RealEstateSmallAd, RealEstateBigAd,
    FinanceBigAd,FinanceSmallAd,
    HealthcareBigAd,HealthcareSmallAd,
    EducationSmallAd,EducationBigAd,
    RestaurantBigAd, RestaurantSmallAd,
    HotelBigAd, HotelSmallAd,
    )
from services.serializers.banners_serializers import (
    GymBigAdSerializer, GymSmallAdSerializer, ProfessionalBigAdSerializer, ProfessionalSmallAdSerializer,
    SaloonBigAdSerializer, SaloonSmallAdSerializer,
    TravelAgencyBigAdSerializer,TravelAgencySmallAdSerializer,
    RealEstateBigAdSerializer, RealEstateSmallAdSerializer,
    FinanceBigAdSerializer,FinanceSmallAdSerializer,
    HealthcareSmallAdSerializer,HealthcareBigAdSerializer,
    EducationBigAdSerializer,EducationSmallAdSerializer,
    RestaurantBigAdSerializer, RestaurantSmallAdSerializer,
    HotelBigAdSerializer, HotelSmallAdSerializer,
)
from services.models.banners import TechIndustryBigAd, TechIndustrySmallAd
from services.serializers.banners_serializers import TechIndustryBigAdSerializer, TechIndustrySmallAdSerializer


class GymBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = GymBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            GymBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = GymBigAd.objects.first()

        # if exists → update
        if obj:
            ser = GymBigAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # else → create first time
        ser = GymBigAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initGymBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = GymBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            GymBigAdSerializer(obj, context={"request": request}).data
        )
    
class GymSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = GymSmallAd.objects.all().order_by("slot")
        return Response(
            GymSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")

        if slot not in ["1", "2", 1, 2]:
            return Response(
                {"error": "slot must be 1 or 2"},
                status=400
            )

        obj = GymSmallAd.objects.filter(slot=slot).first()

        # update if exists
        if obj:
            ser = GymSmallAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # create if not exists yet
        ser = GymSmallAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initGymSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = GymSmallAd.objects.all().order_by("slot")
        return Response(
            GymSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

class SaloonBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = SaloonBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            SaloonBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = SaloonBigAd.objects.first()

        # if exists → update
        if obj:
            ser = SaloonBigAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # else → create first time
        ser = SaloonBigAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initSaloonBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = SaloonBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            SaloonBigAdSerializer(obj, context={"request": request}).data
        )
    
class SaloonSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = SaloonSmallAd.objects.all().order_by("slot")
        return Response(
            SaloonSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")

        if slot not in ["1", "2", 1, 2]:
            return Response(
                {"error": "slot must be 1 or 2"},
                status=400
            )

        obj = SaloonSmallAd.objects.filter(slot=slot).first()

        # update if exists
        if obj:
            ser = SaloonSmallAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # create if not exists yet
        ser = SaloonSmallAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initSaloonSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = SaloonSmallAd.objects.all().order_by("slot")
        return Response(
            SaloonSmallAdSerializer(qs, many=True, context={"request": request}).data
        )
        
class TravelAgencyBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = TravelAgencyBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            TravelAgencyBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = TravelAgencyBigAd.objects.first()

        # if exists → update
        if obj:
            ser = TravelAgencyBigAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # else → create first time
        ser = TravelAgencyBigAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initTravelAgencyBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = TravelAgencyBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            TravelAgencyBigAdSerializer(obj, context={"request": request}).data
        )
    
class TravelAgencySmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = TravelAgencySmallAd.objects.all().order_by("slot")
        return Response(
            TravelAgencySmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")

        if slot not in ["1", "2", 1, 2]:
            return Response(
                {"error": "slot must be 1 or 2"},
                status=400
            )

        obj = TravelAgencySmallAd.objects.filter(slot=slot).first()

        # update if exists
        if obj:
            ser = TravelAgencySmallAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # create if not exists yet
        ser = TravelAgencySmallAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initTravelAgencySmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = TravelAgencySmallAd.objects.all().order_by("slot")
        return Response(
            TravelAgencySmallAdSerializer(qs, many=True, context={"request": request}).data
        )
        
class RealEstateBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = RealEstateBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            RealEstateBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = RealEstateBigAd.objects.first()

        # if exists → update
        if obj:
            ser = RealEstateBigAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # else → create first time
        ser = RealEstateBigAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initRealEstateBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = RealEstateBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            RealEstateBigAdSerializer(obj, context={"request": request}).data
        )
    
class RealEstateSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = RealEstateSmallAd.objects.all().order_by("slot")
        return Response(
            RealEstateSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")

        if slot not in ["1", "2", 1, 2]:
            return Response(
                {"error": "slot must be 1 or 2"},
                status=400
            )

        obj = RealEstateSmallAd.objects.filter(slot=slot).first()

        # update if exists
        if obj:
            ser = RealEstateSmallAdSerializer(
                obj,
                data=request.data,
                partial=True,
                context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)

        # create if not exists yet
        ser = RealEstateSmallAdSerializer(
            data=request.data,
            context={"request": request}
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initRealEstateSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = RealEstateSmallAd.objects.all().order_by("slot")
        return Response(
            RealEstateSmallAdSerializer(qs, many=True, context={"request": request}).data
        )
        
# ==================== TECH INDUSTRY BIG AD ====================
class TechIndustryBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = TechIndustryBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            TechIndustryBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = TechIndustryBigAd.objects.first()
        if obj:
            ser = TechIndustryBigAdSerializer(obj, data=request.data, partial=True, context={"request": request})
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = TechIndustryBigAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initTechIndustryBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = TechIndustryBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            TechIndustryBigAdSerializer(obj, context={"request": request}).data
        )

# ==================== TECH INDUSTRY SMALL ADS ====================
class TechIndustrySmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = TechIndustrySmallAd.objects.all().order_by("slot")
        return Response(
            TechIndustrySmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")
        if slot not in ["1", "2", 1, 2]:
            return Response({"error": "slot must be 1 or 2"}, status=400)
        obj = TechIndustrySmallAd.objects.filter(slot=slot).first()
        if obj:
            ser = TechIndustrySmallAdSerializer(obj, data=request.data, partial=True, context={"request": request})
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = TechIndustrySmallAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)
    
class initTechIndustrySmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = TechIndustrySmallAd.objects.all().order_by("slot")
        return Response(
            TechIndustrySmallAdSerializer(qs, many=True, context={"request": request}).data
        )        
        
        
class ProfessionalBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = ProfessionalBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            ProfessionalBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = ProfessionalBigAd.objects.first()
        if obj:
            ser = ProfessionalBigAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = ProfessionalBigAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initProfessionalBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = ProfessionalBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            ProfessionalBigAdSerializer(obj, context={"request": request}).data
        )


class ProfessionalSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = ProfessionalSmallAd.objects.all().order_by("slot")
        return Response(
            ProfessionalSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")
        if slot not in ["1", "2", 1, 2]:
            return Response({"error": "slot must be 1 or 2"}, status=400)
        obj = ProfessionalSmallAd.objects.filter(slot=slot).first()
        if obj:
            ser = ProfessionalSmallAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = ProfessionalSmallAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initProfessionalSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = ProfessionalSmallAd.objects.all().order_by("slot")
        return Response(
            ProfessionalSmallAdSerializer(qs, many=True, context={"request": request}).data
        )   
        
class FinanceBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = FinanceBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            FinanceBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = FinanceBigAd.objects.first()
        if obj:
            ser = FinanceBigAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = FinanceBigAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initFinanceBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = FinanceBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            FinanceBigAdSerializer(obj, context={"request": request}).data
        )


class FinanceSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = FinanceSmallAd.objects.all().order_by("slot")
        return Response(
            FinanceSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")
        if slot not in ["1", "2", 1, 2]:
            return Response({"error": "slot must be 1 or 2"}, status=400)
        obj = FinanceSmallAd.objects.filter(slot=slot).first()
        if obj:
            ser = FinanceSmallAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = FinanceSmallAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initFinanceSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = FinanceSmallAd.objects.all().order_by("slot")
        return Response(
            FinanceSmallAdSerializer(qs, many=True, context={"request": request}).data
        )             
        
class HealthcareBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = HealthcareBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            HealthcareBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = HealthcareBigAd.objects.first()
        if obj:
            ser = HealthcareBigAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = HealthcareBigAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initHealthcareBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = HealthcareBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            HealthcareBigAdSerializer(obj, context={"request": request}).data
        )


class HealthcareSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = HealthcareSmallAd.objects.all().order_by("slot")
        return Response(
            HealthcareSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")
        if slot not in ["1", "2", 1, 2]:
            return Response({"error": "slot must be 1 or 2"}, status=400)
        obj = HealthcareSmallAd.objects.filter(slot=slot).first()
        if obj:
            ser = HealthcareSmallAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = HealthcareSmallAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initHealthcareSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = HealthcareSmallAd.objects.all().order_by("slot")
        return Response(
            HealthcareSmallAdSerializer(qs, many=True, context={"request": request}).data
        )        


class EducationBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = EducationBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            EducationBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = EducationBigAd.objects.first()
        if obj:
            ser = EducationBigAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = EducationBigAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initEducationBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = EducationBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            EducationBigAdSerializer(obj, context={"request": request}).data
        )


class EducationSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = EducationSmallAd.objects.all().order_by("slot")
        return Response(
            EducationSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")
        if slot not in ["1", "2", 1, 2]:
            return Response({"error": "slot must be 1 or 2"}, status=400)
        obj = EducationSmallAd.objects.filter(slot=slot).first()
        if obj:
            ser = EducationSmallAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = EducationSmallAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initEducationSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = EducationSmallAd.objects.all().order_by("slot")
        return Response(
            EducationSmallAdSerializer(qs, many=True, context={"request": request}).data
        ) 
        
        
class RestaurantBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = RestaurantBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            RestaurantBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = RestaurantBigAd.objects.first()
        if obj:
            ser = RestaurantBigAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = RestaurantBigAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initRestaurantBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = RestaurantBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            RestaurantBigAdSerializer(obj, context={"request": request}).data
        )


class RestaurantSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = RestaurantSmallAd.objects.all().order_by("slot")
        return Response(
            RestaurantSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")
        if slot not in ["1", "2", 1, 2]:
            return Response({"error": "slot must be 1 or 2"}, status=400)
        obj = RestaurantSmallAd.objects.filter(slot=slot).first()
        if obj:
            ser = RestaurantSmallAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = RestaurantSmallAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initRestaurantSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = RestaurantSmallAd.objects.all().order_by("slot")
        return Response(
            RestaurantSmallAdSerializer(qs, many=True, context={"request": request}).data
        ) 
        
class HotelBigAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        obj = HotelBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            HotelBigAdSerializer(obj, context={"request": request}).data
        )

    def post(self, request):
        obj = HotelBigAd.objects.first()
        if obj:
            ser = HotelBigAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = HotelBigAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initHotelBigAdView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        obj = HotelBigAd.objects.first()
        if not obj:
            return Response(None)
        return Response(
            HotelBigAdSerializer(obj, context={"request": request}).data
        )


class HotelSmallAdView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        qs = HotelSmallAd.objects.all().order_by("slot")
        return Response(
            HotelSmallAdSerializer(qs, many=True, context={"request": request}).data
        )

    def post(self, request):
        slot = request.data.get("slot")
        if slot not in ["1", "2", 1, 2]:
            return Response({"error": "slot must be 1 or 2"}, status=400)
        obj = HotelSmallAd.objects.filter(slot=slot).first()
        if obj:
            ser = HotelSmallAdSerializer(
                obj, data=request.data, partial=True, context={"request": request}
            )
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        ser = HotelSmallAdSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data, status=201)


class initHotelSmallAdsView(APIView):
    permission_classes = [AllowAny]
    def get(self, request):
        qs = HotelSmallAd.objects.all().order_by("slot")
        return Response(
            HotelSmallAdSerializer(qs, many=True, context={"request": request}).data
        )                                