from rest_framework import serializers

from apps.core.data_engine import (
    FILL_STRATEGIES,
    SUPPORTED_CASTS,
    SUPPORTED_FORMULAS,
    OUTLIER_METHODS,
    OUTLIER_IMPUTE_STRATEGIES,
    COLUMN_TRANSFORMS,
    FILTER_OPERATORS,
    STRING_OPERATIONS,
    SCALE_METHODS,
    DATETIME_FEATURES,
    ENCODE_STRATEGIES,
)

_DEDUP_MODES = ("all_first", "all_last", "subset_keep", "drop_all")


class CastColumnsSerializer(serializers.Serializer):
    casts = serializers.DictField(
        child=serializers.ChoiceField(choices=list(SUPPORTED_CASTS)),
        allow_empty=False,
    )
    force = serializers.BooleanField(default=False, required=False)


class UpdateCellSerializer(serializers.Serializer):
    row_index = serializers.IntegerField(min_value=0)
    column = serializers.CharField()
    value = serializers.JSONField(allow_null=True)


class RenameColumnSerializer(serializers.Serializer):
    old_name = serializers.CharField()
    new_name = serializers.CharField()

    def validate(self, data):
        if data["old_name"].strip() == data["new_name"].strip():
            raise serializers.ValidationError("new_name must differ from old_name.")
        return data


class DropDuplicatesSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=_DEDUP_MODES, default="all_first")
    subset = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    keep = serializers.ChoiceField(choices=["first", "last"], default="first", required=False)

    def validate(self, data):
        if data.get("mode") == "subset_keep":
            if not data.get("subset"):
                raise serializers.ValidationError({"subset": "Required when mode is 'subset_keep'."})
            if data.get("keep") not in ("first", "last"):
                raise serializers.ValidationError({"keep": "Must be 'first' or 'last' for mode 'subset_keep'."})
        return data


class ReplaceValuesSerializer(serializers.Serializer):
    replacements = serializers.DictField(allow_empty=False)
    columns = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    confirm_global = serializers.BooleanField(default=False, required=False)

    def validate(self, data):
        if data.get("columns") is None and not data.get("confirm_global"):
            raise serializers.ValidationError(
                {"columns": "Required, or pass confirm_global=true to replace across all columns."}
            )
        return data


class DropNullsSerializer(serializers.Serializer):
    axis = serializers.ChoiceField(choices=["rows", "columns"], default="rows")
    how = serializers.ChoiceField(choices=["any", "all"], default="any", required=False)
    subset = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    thresh_pct = serializers.FloatField(min_value=0, max_value=100, required=False, allow_null=True)

    def validate(self, data):
        if data.get("axis") == "columns" and data.get("thresh_pct") is None:
            raise serializers.ValidationError({"thresh_pct": "Required when axis is 'columns'."})
        return data


class FillNullsSerializer(serializers.Serializer):
    strategy = serializers.ChoiceField(choices=list(FILL_STRATEGIES))
    columns = serializers.ListField(child=serializers.CharField(), required=False, allow_null=True)
    value = serializers.JSONField(required=False, allow_null=True)

    def validate(self, data):
        if data.get("strategy") == "constant" and data.get("value") is None:
            raise serializers.ValidationError({"value": "Required when strategy is 'constant'."})
        return data


class FormulaSerializer(serializers.Serializer):
    """Base for fill_derived / fix_formula / validate_formula."""
    target = serializers.CharField()
    formula = serializers.ChoiceField(choices=list(SUPPORTED_FORMULAS))
    operand_a = serializers.CharField()
    operand_b = serializers.CharField()
    tolerance = serializers.FloatField(min_value=1e-9, default=0.01, required=False)


class AddColumnSerializer(serializers.Serializer):
    new_name = serializers.CharField()
    formula = serializers.ChoiceField(choices=list(SUPPORTED_FORMULAS))
    operand_a = serializers.CharField()
    operand_b = serializers.CharField()


class OutlierParamsSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    method = serializers.ChoiceField(choices=list(OUTLIER_METHODS), default="iqr")
    threshold = serializers.FloatField(min_value=1e-9, max_value=10, default=1.5)


class ImputeOutliersSerializer(OutlierParamsSerializer):
    strategy = serializers.ChoiceField(choices=list(OUTLIER_IMPUTE_STRATEGIES), default="median")


class CapOutliersSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    lower_pct = serializers.FloatField(min_value=0, max_value=99.9, default=5.0)
    upper_pct = serializers.FloatField(min_value=0.1, max_value=100, default=95.0)

    def validate(self, data):
        if data["lower_pct"] >= data["upper_pct"]:
            raise serializers.ValidationError("lower_pct must be less than upper_pct.")
        return data


class TransformColumnSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    function = serializers.ChoiceField(choices=list(COLUMN_TRANSFORMS), default="log")


class DropColumnsSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField(), allow_empty=False)


class FilterRowsSerializer(serializers.Serializer):
    column = serializers.CharField()
    operator = serializers.ChoiceField(choices=list(FILTER_OPERATORS))
    value = serializers.JSONField(required=False, allow_null=True)

    def validate(self, data):
        if data.get("operator") not in ("isnull", "notnull") and data.get("value") is None:
            raise serializers.ValidationError({"value": f"Required for operator '{data['operator']}'."})
        return data


class CleanStringSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    operation = serializers.ChoiceField(choices=list(STRING_OPERATIONS))


class ScaleColumnsSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    method = serializers.ChoiceField(choices=list(SCALE_METHODS), default="minmax")


class ExtractDatetimeSerializer(serializers.Serializer):
    column = serializers.CharField()
    features = serializers.ListField(
        child=serializers.ChoiceField(choices=list(DATETIME_FEATURES)),
        allow_empty=False,
    )


class EncodeColumnsSerializer(serializers.Serializer):
    columns = serializers.ListField(child=serializers.CharField(), allow_empty=False)
    strategy = serializers.ChoiceField(choices=list(ENCODE_STRATEGIES), default="label")
