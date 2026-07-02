from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('ecommerce', '0026_alter_customerprofile_email_and_more'),
        ('services', '0008_healthcarebigad_healthcareserviceimage_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [

        # ── Step 1: Purane education tables safely drop karo (IF EXISTS) ──
        migrations.RunSQL(
            sql="""
                SET FOREIGN_KEY_CHECKS = 0;
                DROP TABLE IF EXISTS services_educationservice_multi_images;
                DROP TABLE IF EXISTS services_educationcourse;
                DROP TABLE IF EXISTS services_educationimage;
                DROP TABLE IF EXISTS services_educationservice;
                SET FOREIGN_KEY_CHECKS = 1;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        # ── Step 2: Naye tables safely drop karo pehle (agar partial create hua ho) ──
        migrations.RunSQL(
            sql="""
                SET FOREIGN_KEY_CHECKS = 0;
                DROP TABLE IF EXISTS services_educationbigad;
                DROP TABLE IF EXISTS services_educationsmallad;
                DROP TABLE IF EXISTS education_new_service_multi_images;
                DROP TABLE IF EXISTS education_new_service;
                DROP TABLE IF EXISTS services_educationnewserviceimage;
                SET FOREIGN_KEY_CHECKS = 1;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        # ── Step 3: Django state update karo (DB se already handle ho gaya upar) ──
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name='EducationCourse'),
                migrations.DeleteModel(name='EducationImage'),
                migrations.RemoveField(model_name='educationservice', name='multi_images'),
                migrations.RemoveField(model_name='educationservice', name='approved_by'),
                migrations.RemoveField(model_name='educationservice', name='subcategory'),
                migrations.RemoveField(model_name='educationservice', name='vendor'),
                migrations.DeleteModel(name='EducationService'),
            ],
            database_operations=[],  # DB mein already Step 1 ne handle kiya
        ),

        # ── Step 4: Naye models create karo ──
        migrations.CreateModel(
            name='EducationBigAd',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='ads/education-big/')),
                ('title', models.CharField(max_length=200)),
                ('url', models.URLField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='EducationNewServiceImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='education_new_services/multi/')),
            ],
        ),
        migrations.CreateModel(
            name='EducationNewService',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_active', models.BooleanField(default=True)),
                ('business_name', models.CharField(max_length=255)),
                ('address', models.TextField()),
                ('location', models.CharField(blank=True, help_text='Google Maps link', max_length=500, null=True)),
                ('country', models.CharField(blank=True, max_length=100, null=True)),
                ('state', models.CharField(blank=True, max_length=100, null=True)),
                ('city', models.CharField(blank=True, max_length=100, null=True)),
                ('contact_no', models.CharField(max_length=20)),
                ('whatsapp_no', models.CharField(blank=True, max_length=20, null=True)),
                ('gmail_id', models.EmailField(blank=True, max_length=255, null=True)),
                ('description', models.TextField()),
                ('main_image', models.ImageField(blank=True, null=True, upload_to='education_new_services/')),
                ('status', models.CharField(
                    choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')],
                    default='pending', max_length=20
                )),
                ('approved_date', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('approved_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='approved_education_new_services',
                    to=settings.AUTH_USER_MODEL
                )),
                ('subcategory', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    to='services.servicesubcategory'
                )),
                ('vendor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='education_new_services',
                    to='ecommerce.vendor'
                )),
                ('multi_images', models.ManyToManyField(blank=True, to='services.educationnewserviceimage')),
            ],
            options={
                'db_table': 'education_new_service',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='EducationSmallAd',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slot', models.PositiveSmallIntegerField()),
                ('image', models.ImageField(upload_to='ads/education-small/')),
                ('title', models.CharField(max_length=200)),
                ('url', models.URLField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'unique_together': {('slot',)},
            },
        ),
    ]