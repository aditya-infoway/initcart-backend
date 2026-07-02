from django.db import models
   
class GymBigAd(models.Model):
    image = models.ImageField(upload_to="ads/gym-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class GymSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/gym-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]  # only 2 fixed slots

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"

class SaloonBigAd(models.Model):
    image = models.ImageField(upload_to="ads/saloon-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class SaloonSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/saloon-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]  # only 2 fixed slots

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"

class TravelAgencyBigAd(models.Model):
    image = models.ImageField(upload_to="ads/TravelAgency-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class TravelAgencySmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/TravelAgency-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]  # only 2 fixed slots

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"

class RealEstateBigAd(models.Model):
    image = models.ImageField(upload_to="ads/RealEstate-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class RealEstateSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/RealEstate-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]  # only 2 fixed slots

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"
    
class TechIndustryBigAd(models.Model):
    image = models.ImageField(upload_to="ads/techindustry-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class TechIndustrySmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/techindustry-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"    
    
class ProfessionalBigAd(models.Model):
    image = models.ImageField(upload_to="ads/professional-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ProfessionalSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/professional-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"   
    
    
class FinanceBigAd(models.Model):
    image = models.ImageField(upload_to="ads/finance-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class FinanceSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/fianance-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"        
    
class HealthcareBigAd(models.Model):
    image = models.ImageField(upload_to="ads/healthcare-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class HealthcareSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/healthcare-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"     
    
class EducationBigAd(models.Model):
    image = models.ImageField(upload_to="ads/education-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class EducationSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()
    image = models.ImageField(upload_to="ads/education-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"
    
class RestaurantBigAd(models.Model):
    image = models.ImageField(upload_to="ads/restaurant-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class RestaurantSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/restaurant-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]

    def __str__(self):
        return f"Slot {self.slot} - {self.title}" 
    
class HotelBigAd(models.Model):
    image = models.ImageField(upload_to="ads/hotel-big/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class HotelSmallAd(models.Model):
    slot = models.PositiveSmallIntegerField()  # 1 or 2
    image = models.ImageField(upload_to="ads/hotel-small/")
    title = models.CharField(max_length=200)
    url = models.URLField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["slot"]

    def __str__(self):
        return f"Slot {self.slot} - {self.title}"       