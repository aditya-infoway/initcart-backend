# serializers/journal_serializer.py
from rest_framework import serializers
from pos.models.journalentries import JournalEntry,JournalMaster

class JournalEntrySerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(
        source="account.account_name",
        read_only=True
    )
    class Meta:
        model = JournalEntry
        fields = ("account","account_name", "debit", "credit", "narration")

class JournalMasterSerializer(serializers.ModelSerializer):
    entries = JournalEntrySerializer(many=True)

    class Meta:
        model = JournalMaster
        fields = (
            "date",
            "voucher_no",
            "reference_no",
            "total_debit",
            "total_credit",
            "entries",
        )

    def create(self, validated_data):
        branch = self.context.get("branch")  # <-- use context instead of data
        if branch:
            validated_data["branch"] = branch
        # return super().create(validated_data)
        entries_data = validated_data.pop("entries")

        journal = JournalMaster.objects.create(**validated_data)

        for entry in entries_data:
            JournalEntry.objects.create(journal=journal, **entry)

        return journal
