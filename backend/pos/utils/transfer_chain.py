# pos/utils/transfer_chain.py
"""
✅ NEW — Item kahan se kahan tak transfer hoke current branch tak pahunchi,
uska PURA CHAIN barcode ke through reverse-walk karke nikalta hai.

Kyun barcode se?
  Har branch ka apna alag Items/ItemVariants row hota hai (copy-on-transfer
  pattern already existing code mein hai — create_full_item_in_destination).
  Isliye FK se direct chain nahi bana sakte; barcode hi stable common
  identifier hai jo superadmin → branch A → branch B ... sab jagah same
  rehta hai.

Chain do tarah ke "hops" se banti hai:
  1. stock_transfer  → Superadmin (company) branch ne kisi branch ko diya
  2. b2b_transfer    → Ek branch ne doosri branch ko diya (B2B)

Return hamesha LAST branch (jisne abhi return kiya) se superadmin tak
hota hai, lekin superadmin ko dikhana hai ki yeh item ORIGINALLY kab/kaise
superadmin se nikli thi aur beech mein kitni branches se hoke guzri.
"""

from pos.models.stock_transfer import StockTransferItem
from pos.models.b2b_transfer import B2BStockTransferItem


def build_transfer_chain(branch, barcode, max_hops=15):
    """
    `branch` tak `barcode` wala item kaise pahuncha, uska ordered list
    (origin se current branch tak) return karta hai.

    Har hop:
    {
        'hop_type': 'stock_transfer' | 'b2b_transfer',
        'hop_label': 'Company Stock Transfer' | 'Branch to Branch (B2B) Transfer',
        'transfer_no': str,
        'from_branch_name': str,
        'to_branch_name': str,
        'transfer_date': str,
        'quantity': int,
        'status': str,
    }
    """
    if not barcode:
        return []

    chain = []
    current_branch = branch
    visited_branch_ids = set()

    for _ in range(max_hops):
        if not current_branch or current_branch.id in visited_branch_ids:
            break
        visited_branch_ids.add(current_branch.id)

        #  Pehle check karo — is branch ko yeh item kisi DOOSRI branch se
        # B2B transfer ke through mila tha kya?
        b2b_item = (
            B2BStockTransferItem.objects
            .filter(
                transfer__to_branch=current_branch,
                from_barcode=barcode,
                is_received=True,
            )
            .select_related('transfer', 'transfer__from_branch', 'transfer__to_branch')
            .order_by('-transfer__created_at')
            .first()
        )

        if b2b_item:
            chain.insert(0, {
                'hop_type': 'b2b_transfer',
                'hop_label': 'Branch to Branch (B2B) Transfer',
                'transfer_no': b2b_item.transfer.transfer_no,
                'from_branch_name': b2b_item.transfer.from_branch.branch_name,
                'to_branch_name': b2b_item.transfer.to_branch.branch_name,
                'transfer_date': str(b2b_item.transfer.transfer_date),
                'quantity': b2b_item.quantity,
                'status': b2b_item.transfer.status,
            })
            #  Ab peeche jao — is B2B transfer ki from_branch ko yeh item
            # kahan se mili thi (superadmin se ya kisi teesri branch se)
            current_branch = b2b_item.transfer.from_branch
            continue

        #  Warna check karo — seedha superadmin (company) se Stock Transfer
        # ke through mila tha kya? Yeh mile toh CHAIN KA ROOT hai, ruk jao.
        st_item = (
            StockTransferItem.objects
            .filter(
                transfer__to_branch=current_branch,
                from_barcode=barcode,
                is_stock_updated=True,
            )
            .select_related('transfer', 'transfer__from_branch', 'transfer__to_branch')
            .order_by('-transfer__created_at')
            .first()
        )

        if st_item:
            chain.insert(0, {
                'hop_type': 'stock_transfer',
                'hop_label': 'Company Stock Transfer',
                'transfer_no': st_item.transfer.transfer_no,
                'from_branch_name': st_item.transfer.from_branch.branch_name,
                'to_branch_name': st_item.transfer.to_branch.branch_name,
                'transfer_date': str(st_item.transfer.transfer_date),
                'quantity': st_item.quantity,
                'status': st_item.transfer.status,
            })
            break  # ✅ Root mil gaya (superadmin), aage jaane ki zaroorat nahi

        # Koi hop nahi mila — chain yahin incomplete reh jaayegi (edge case,
        # jaise bahut purana data jisme to_variant/barcode match nahi hua)
        break

    return chain


def get_origin_branch_name(branch, barcode):
    """Chain ka sabse pehla (root/origin) branch name — usually superadmin/company."""
    chain = build_transfer_chain(branch, barcode)
    if chain:
        return chain[0]['from_branch_name']
    return None