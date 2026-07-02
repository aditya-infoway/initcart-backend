from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pos', '0032_salesmaster_unique_bill_per_branch'),
    ]

    operations = [
        # ✅ PurchaseReturnMaster
        migrations.AlterField(
            model_name='purchasereturnmaster',
            name='return_no',
            field=models.CharField(max_length=50),
        ),
        migrations.AddConstraint(
            model_name='purchasereturnmaster',
            constraint=models.UniqueConstraint(
                fields=['branch', 'return_no'],
                name='unique_pr_per_branch'
            ),
        ),

        # ✅ SalesReturnMaster
        migrations.AlterField(
            model_name='salesreturnmaster',
            name='return_no',
            field=models.CharField(max_length=50),
        ),
        migrations.AddConstraint(
            model_name='salesreturnmaster',
            constraint=models.UniqueConstraint(
                fields=['branch', 'return_no'],
                name='unique_sr_per_branch'
            ),
        ),

        # ✅ BankReceipt
        migrations.AlterField(
            model_name='bankreceipt',
            name='voucher_no',
            field=models.CharField(max_length=50),
        ),
        migrations.AddConstraint(
            model_name='bankreceipt',
            constraint=models.UniqueConstraint(
                fields=['branch', 'voucher_no'],
                name='unique_br_per_branch'
            ),
        ),

        # ✅ CashReceipt
        migrations.AlterField(
            model_name='cashreceipt',
            name='voucher_no',
            field=models.CharField(max_length=50),
        ),
        migrations.AddConstraint(
            model_name='cashreceipt',
            constraint=models.UniqueConstraint(
                fields=['branch', 'voucher_no'],
                name='unique_cr_per_branch'
            ),
        ),
    ]