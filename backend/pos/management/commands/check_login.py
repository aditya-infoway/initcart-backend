"""
Usage:
    python manage.py check_login superee@gmail.com super1212

Isse HTTP ke bina, seedha DB aur auth logic test hoti hai —
jo bhi step fail hoga wahi asli root cause hai.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import authenticate, get_user_model
from django.db import connection

User = get_user_model()


class Command(BaseCommand):
    help = "Diagnose login issues for employee/branch/superadmin"

    def add_arguments(self, parser):
        parser.add_argument("identifier", type=str)
        parser.add_argument("password", type=str)

    def handle(self, *args, **options):
        identifier = options["identifier"].strip()
        password = options["password"].strip()

        self.stdout.write(self.style.WARNING(f"\n=== Checking login for: {identifier} ===\n"))

        # STEP 1: Employee table exists check
        self.stdout.write("[1] Checking if pos_employee table exists...")
        table_names = connection.introspection.table_names()
        if "pos_employee" in table_names:
            self.stdout.write(self.style.SUCCESS("    OK: pos_employee table exists"))
        else:
            self.stdout.write(self.style.ERROR(
                "    MISSING: pos_employee table NOT found in DB. "
                "Run: python manage.py makemigrations pos && python manage.py migrate"
            ))

        if "pos_employeepermission" in table_names:
            self.stdout.write(self.style.SUCCESS("    OK: pos_employeepermission table exists"))
        else:
            self.stdout.write(self.style.ERROR("    MISSING: pos_employeepermission table NOT found in DB."))

        # STEP 2: Try importing Employee model (catches circular import)
        self.stdout.write("\n[2] Trying to import Employee model...")
        try:
            from pos.models.employee import Employee
            self.stdout.write(self.style.SUCCESS("    OK: Employee model imported successfully"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    IMPORT ERROR: {type(e).__name__}: {e}"))
            self.stdout.write(self.style.ERROR("    ^ Ye circular import ya syntax error hai. Fix karo pehle."))
            return

        # STEP 3: Try querying Employee table
        self.stdout.write("\n[3] Trying to query Employee table...")
        try:
            emp_count = Employee.objects.count()
            self.stdout.write(self.style.SUCCESS(f"    OK: Query worked. Total employees in DB: {emp_count}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    QUERY ERROR: {type(e).__name__}: {e}"))
            self.stdout.write(self.style.ERROR("    ^ Ye migration missing hone ka pakka sign hai."))
            return

        # STEP 4: Check if this identifier matches an Employee
        self.stdout.write("\n[4] Checking if identifier matches an Employee record...")
        from django.db.models import Q
        employee = Employee.objects.filter(
            Q(email__iexact=identifier) | Q(mobile=identifier)
        ).select_related("user", "branch").first()

        if employee:
            self.stdout.write(self.style.SUCCESS(f"    FOUND employee: {employee.full_name} (status={employee.status})"))
        else:
            self.stdout.write(self.style.WARNING("    NOT an employee -> this identifier should go to superadmin/branch login path"))

        # STEP 5: Check User table directly
        self.stdout.write("\n[5] Checking User table for this identifier...")
        user_obj = User.objects.filter(email__iexact=identifier).first()
        if user_obj:
            self.stdout.write(self.style.SUCCESS(
                f"    FOUND user: username={user_obj.username}, role={user_obj.role}, "
                f"is_active={user_obj.is_active}"
            ))
        else:
            self.stdout.write(self.style.ERROR("    NO User found with this email at all."))
            self.stdout.write(self.style.ERROR("    ^ Login hamesha fail hoga jab tak User exist nahi karta."))
            return

        # STEP 6: Try Django authenticate() directly
        self.stdout.write("\n[6] Trying authenticate(username=..., password=...)...")
        auth_result = authenticate(username=user_obj.username, password=password)
        if auth_result:
            self.stdout.write(self.style.SUCCESS(f"    SUCCESS: authenticate() worked for username={user_obj.username}"))
        else:
            self.stdout.write(self.style.ERROR(
                f"    FAILED: authenticate() returned None for username={user_obj.username}"
            ))
            self.stdout.write(self.style.ERROR(
                "    ^ Password galat hai, YA user.is_active=False hai, YA username mismatch hai."
            ))
            self.stdout.write(self.style.WARNING(
                f"    Check karo ki user.check_password('{password}') manually kya deta hai:"
            ))
            self.stdout.write(self.style.WARNING(
                f"    -> user_obj.check_password result: {user_obj.check_password(password)}"
            ))

        # STEP 7: Check Branch table too (in case this is a branch/superadmin identifier)
        self.stdout.write("\n[7] Checking Branch table for this identifier...")
        try:
            from pos.models.branch import Branch
            branch_obj = Branch.objects.filter(Q(email=identifier) | Q(phone=identifier)).select_related("user").first()
            if branch_obj:
                self.stdout.write(self.style.SUCCESS(
                    f"    FOUND branch: {branch_obj.branch_name}, status={branch_obj.status}, "
                    f"has_branch_password={'yes' if branch_obj.password else 'no'}, "
                    f"user_role={branch_obj.user.role if branch_obj.user else 'NO USER LINKED'}"
                ))
            else:
                self.stdout.write(self.style.WARNING("    No Branch record found with this email/phone"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    ERROR checking Branch: {type(e).__name__}: {e}"))

        self.stdout.write(self.style.WARNING("\n=== Done ===\n"))