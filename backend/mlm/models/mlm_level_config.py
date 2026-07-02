from django.db import models

class MLMLevelConfig(models.Model):

    name = models.CharField(max_length=100, default="Default MLM Config")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name