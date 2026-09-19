from pos.models.items import items as Items, itemvariants as ItemVariants, VariantPurchasePriceHistory
from pos.models.stock_transfer import VariantBranchMapping


def _log_price_change(variant, old_price, new_price, source, reference):
    """
    Sirf tab entry save karo jab price GENUINELY badli ho (ya pehli baar
    create hui ho — old_price=None). Same price dobara save hone par
    (no-op sync) duplicate history row nahi banegi.
    """
    old_val = float(old_price) if old_price is not None else None
    new_val = float(new_price or 0)
    if old_val is not None and old_val == new_val:
        return
    VariantPurchasePriceHistory.objects.create(
        variant=variant,
        old_price=old_val,
        new_price=new_val,
        source=source,
        reference=reference,
    )


def get_or_create_dest_variant(from_variant, to_branch, sync_fields=False, price_override=None,
                                source=None, reference=None):
    """
    from_variant  -> superadmin/source variant
    to_branch     -> destination branch
    sync_fields   -> True sirf tab jab ACTUAL stock transfer verify ho raha ho.
                      Tab hi destination variant ke fields (barcode/price/etc.)
                      current source values se sync honge.
                      False = sirf existence ensure karo, fields mat chhedo
                      (item-copy / pre-create ke waqt use hota hai).
    price_override -> Diya gaya ho to purchasePrice/branchPrice ISI value se set
                      hoga (from_variant.branchPrice ko IGNORE karke). B2B Sale
                      verify flow yaha B2BSaleItem.rate bhejta hai — jo us sale
                      me ACTUALLY charge hui price hai (Excel import se custom
                      Franchise Price bhi ho sakti hai) — taaki destination
                      branch ka purchase price wahi ho jo B2B sale me tha, na
                      ki source branch ka AAJ ka live branchPrice.
                      None (default) = purana behavior — Stock Transfer flow
                      isse touch nahi karta, isliye uska behavior same rahega.
    source, reference -> Sirf history logging ke liye (e.g. source="B2B Sale",
                      reference=sale.sale_no). None chhod do to bhi kaam
                      karega, bas history row me "—" dikhega.
    Returns: (dest_variant, created: bool)
    """
    def _resolve_price():
        if price_override is not None:
            return price_override or 0
        return from_variant.branchPrice or 0

    mapping = VariantBranchMapping.objects.filter(
        source_variant=from_variant, to_branch=to_branch
    ).select_related('dest_variant').first()

    if mapping:
        dest_variant = mapping.dest_variant
        if sync_fields:
            branch_price = _resolve_price()
            old_purchase_price = dest_variant.purchasePrice
            dest_variant.barcode = from_variant.barcode
            dest_variant.mrp = from_variant.mrp
            dest_variant.salesPrice = from_variant.salesPrice
            dest_variant.purchasePrice = branch_price
            dest_variant.branchPrice = branch_price
            dest_variant.size = from_variant.size
            dest_variant.color = from_variant.color
            dest_variant.srno = from_variant.srno
            dest_variant.warrantydate = from_variant.warrantydate
            dest_variant.save(update_fields=[
                'barcode', 'mrp', 'salesPrice', 'purchasePrice', 'branchPrice',
                'size', 'color', 'srno', 'warrantydate'
            ])
            # ✅ History — sirf tab jab price genuinely badli ho
            _log_price_change(dest_variant, old_purchase_price, branch_price, source, reference)
        return dest_variant, False

    # ── Mapping nahi mili — pehle check karo ki destination branch me is item ka
    # variant already kisi PURANI (pre-mapping) transfer se ban chuka ho.
    # Agar mil jaaye, toh USI se link kar do (naya duplicate mat banao). ──
    from_item = from_variant.item

    dest_item = Items.objects.filter(
        branch=to_branch, itemName=from_item.itemName, created_by_superadmin=True
    ).first()

    legacy_dest_variant = None
    if dest_item:
        # 1) Sabse bharosemand match: barcode (agar dono me barcode hai)
        if from_variant.barcode:
            legacy_dest_variant = ItemVariants.objects.filter(
                item=dest_item, barcode=from_variant.barcode
            ).exclude(
                # ✅ pehle se kisi doosre source variant se mapped variant mat chhedo
                id__in=VariantBranchMapping.objects.filter(to_branch=to_branch).values_list('dest_variant_id', flat=True)
            ).first()

        # 2) Fallback: size+color match (barcode na ho toh)
        if not legacy_dest_variant:
            legacy_dest_variant = ItemVariants.objects.filter(
                item=dest_item, size=from_variant.size, color=from_variant.color
            ).exclude(
                id__in=VariantBranchMapping.objects.filter(to_branch=to_branch).values_list('dest_variant_id', flat=True)
            ).first()

    if legacy_dest_variant:
        # Purana variant mil gaya — usse hi permanently map kar do, aage se yehi use hoga.
        VariantBranchMapping.objects.create(
            source_variant=from_variant, to_branch=to_branch, dest_variant=legacy_dest_variant
        )
        if sync_fields:
            branch_price = _resolve_price()
            old_purchase_price = legacy_dest_variant.purchasePrice
            legacy_dest_variant.barcode = from_variant.barcode
            legacy_dest_variant.mrp = from_variant.mrp
            legacy_dest_variant.salesPrice = from_variant.salesPrice
            legacy_dest_variant.purchasePrice = branch_price
            legacy_dest_variant.branchPrice = branch_price
            legacy_dest_variant.size = from_variant.size
            legacy_dest_variant.color = from_variant.color
            legacy_dest_variant.srno = from_variant.srno
            legacy_dest_variant.warrantydate = from_variant.warrantydate
            legacy_dest_variant.save(update_fields=[
                'barcode', 'mrp', 'salesPrice', 'purchasePrice', 'branchPrice',
                'size', 'color', 'srno', 'warrantydate'
            ])
            # ✅ History
            _log_price_change(legacy_dest_variant, old_purchase_price, branch_price, source, reference)
        return legacy_dest_variant, False

    # ── Genuinely pehli baar — naya item/variant banao ──
    if not dest_item:
        dest_item = Items.objects.create(
            entry_type=from_item.entry_type,
            itemName=from_item.itemName,
            branch=to_branch,
            brand=from_item.brand,
            c_brand=from_item.c_brand,
            category=from_item.category,
            c_category=from_item.c_category,
            subCategory=from_item.subCategory,
            c_subCategory=from_item.c_subCategory,
            subSubCategory=from_item.subSubCategory,
            c_subSubCategory=from_item.c_subSubCategory,
            group=from_item.group,
            unit=from_item.unit,
            created_by_superadmin=True,
            hsnCode=from_item.hsnCode,
            taxSlab=from_item.taxSlab,
            website_display=False,
            website_status='pending',
            short_description=from_item.short_description,
            full_description=from_item.full_description,
            keywords=from_item.keywords,
            main_image=from_item.main_image,
            thumbnail_image=from_item.thumbnail_image,
            gallery=from_item.gallery,
            product_condition=from_item.product_condition,
            return_policy=from_item.return_policy,
            estimated_delivery_time=from_item.estimated_delivery_time,
            free_shipping=from_item.free_shipping,
            warranty_available=from_item.warranty_available,
            warranty_period=from_item.warranty_period,
            warranty_type=from_item.warranty_type,
            warranty_description=from_item.warranty_description,
            description_features=from_item.description_features,
            specifications=from_item.specifications,
        )

    branch_price = _resolve_price()
    dest_variant = ItemVariants.objects.create(
        item=dest_item,
        purchasePrice=branch_price,
        salesPrice=from_variant.salesPrice,
        mrp=from_variant.mrp,
        barcode=from_variant.barcode,
        opStock=0,
        current_stock=0,
        size=from_variant.size,
        color=from_variant.color,
        srno=from_variant.srno,
        warrantydate=from_variant.warrantydate,
        variant_image=from_variant.variant_image,
        branchPrice=branch_price,
    )

    VariantBranchMapping.objects.create(
        source_variant=from_variant, to_branch=to_branch, dest_variant=dest_variant
    )
    # ✅ History — initial entry, old_price=None (pehli baar create hui)
    _log_price_change(dest_variant, None, branch_price, source, reference)

    return dest_variant, True