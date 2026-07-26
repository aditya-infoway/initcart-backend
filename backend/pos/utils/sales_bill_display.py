# pos/utils/sales_bill_display.py
from pos.models.branch import Branch
from pos.models.sales_bill_display_setting import SalesBillDisplaySetting


def get_display_branch_for_sale(sale_branch):
    """
    Sale ki original branch dekar, decide karta hai ki receipt/PDF pe
    kis branch ka naam/address dikhana hai.
    - mode='main'   -> hamesha superadmin ki branch
    - mode='branch' -> agar sale_branch selected_branches me hai -> superadmin ki branch
                        warna -> khud sale_branch
    - superadmin branch na mile toh fallback: sale_branch (safe default)
    """
    setting_obj = SalesBillDisplaySetting.get_solo()

    superadmin_branch = Branch.objects.filter(user__role='superadmin').first()
    if not superadmin_branch:
        return sale_branch

    if setting_obj.mode == 'main':
        return superadmin_branch

    if setting_obj.mode == 'branch':
        if setting_obj.selected_branches.filter(id=sale_branch.id).exists():
            return superadmin_branch

    return sale_branch