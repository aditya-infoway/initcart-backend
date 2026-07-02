from rest_framework import serializers
from services.models.banners import (
    GymBigAd, TravelAgencyBigAd, 
    TravelAgencySmallAd, GymSmallAd, 
    SaloonBigAd, SaloonSmallAd,
    RealEstateBigAd, RealEstateSmallAd ,
    ProfessionalBigAd, ProfessionalSmallAd, 
    FinanceBigAd, FinanceSmallAd,
    HealthcareBigAd,HealthcareSmallAd,
    EducationBigAd,EducationSmallAd,
    RestaurantBigAd,RestaurantSmallAd,
    HotelBigAd, HotelSmallAd,
    )

from services.models.banners import TechIndustryBigAd, TechIndustrySmallAd 

class GymBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = GymBigAd
        fields = "__all__"


class GymSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = GymSmallAd
        fields = "__all__"
        
class SaloonBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = SaloonBigAd
        fields = "__all__"


class SaloonSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = SaloonSmallAd
        fields = "__all__"
        
class TravelAgencyBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = TravelAgencyBigAd
        fields = "__all__"


class TravelAgencySmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = TravelAgencySmallAd
        fields = "__all__"
        
class RealEstateBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = RealEstateBigAd
        fields = "__all__"


class RealEstateSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = RealEstateSmallAd
        fields = "__all__"
        
        
class TechIndustryBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = TechIndustryBigAd
        fields = "__all__"


class TechIndustrySmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = TechIndustrySmallAd
        fields = "__all__"        
    

class ProfessionalBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = ProfessionalBigAd
        fields = "__all__"


class ProfessionalSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = ProfessionalSmallAd
        fields = "__all__"        
        
        
class FinanceBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = FinanceBigAd
        fields = "__all__"


class FinanceSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = FinanceSmallAd
        fields = "__all__"           
        
        
class HealthcareBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = HealthcareBigAd
        fields = "__all__"


class HealthcareSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = HealthcareSmallAd
        fields = "__all__"        
 
 
class EducationBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = EducationBigAd
        fields = "__all__"


class EducationSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = EducationSmallAd
        fields = "__all__"        
        
        
class RestaurantBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = RestaurantBigAd
        fields = "__all__"


class RestaurantSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = RestaurantSmallAd
        fields = "__all__"    
        
class HotelBigAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = HotelBigAd
        fields = "__all__"


class HotelSmallAdSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(use_url=True)

    class Meta:
        model = HotelSmallAd
        fields = "__all__"                                    