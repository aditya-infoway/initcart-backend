"""
Usage:
    python manage.py list_logins

DB me jo bhi valid login identifiers hain (superadmin, branch, employee)
sabko list kar dega — taaki pata chale sahi credential kya hai.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "List all valid login identifiers currently in the DB"

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("\n=== SUPERADMIN Users ===\n"))
        superadmins = User.objects.filter(role="superadmin")
        if not superadmins.exists():
            self.stdout.write(self.style.ERROR("    No superadmin user found in DB!"))
        for u in superadmins:
            self.stdout.write(f"    email={u.email}  username={u.username}  is_active={u.is_active}")

        self.stdout.write(self.style.WARNING("\n=== BRANCH records ===\n"))
        try:
            from pos.models.branch import Branch
            branches = Branch.objects.all().select_related("user")
            if not branches.exists():
                self.stdout.write(self.style.ERROR("    No Branch records found in DB!"))
            for b in branches:
                role = b.user.role if b.user else "NO USER LINKED"
                self.stdout.write(
                    f"    branch_name={b.branch_name}  email={b.email}  phone={b.phone}  "
                    f"status={b.status}  linked_user_role={role}  "
                    f"has_own_branch_password={'yes' if b.password else 'no'}"
                )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    Error reading Branch table: {e}"))

        self.stdout.write(self.style.WARNING("\n=== EMPLOYEE records ===\n"))   
        try:
            from pos.models.employee import Employee
            employees = Employee.objects.all().select_related("branch")
            if not employees.exists():
                self.stdout.write(self.style.ERROR("    No Employee records found in DB! (Employee create form se koi employee abhi tak bana hi nahi)"))
            for e in employees:
                self.stdout.write(
                    f"    full_name={e.full_name}  email={e.email}  department={e.department}  "
                    f"status={e.status}  branch={e.branch.branch_name}"
                )
        except Exception as ex:
            self.stdout.write(self.style.ERROR(f"    Error reading Employee table: {ex}"))

        self.stdout.write(self.style.WARNING("\n=== Done. Ab in me se koi bhi email/phone + apna password use karke login test karo ===\n"))