from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('datasets', '0007_add_datalab_action_choices'),
    ]

    operations = [
        migrations.AlterField(
            model_name='datasetactivitylog',
            name='action',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('UPLOAD', 'Upload'),
                    ('RENAME', 'Rename'),
                    ('DELETE', 'Delete'),
                    ('DUPLICATE', 'Duplicate'),
                    ('EXPORT', 'Export'),
                    ('UPDATE_CELL', 'Update Cell'),
                    ('PREVIEW', 'Preview'),
                    ('DIAGNOSE', 'Diagnose'),
                    ('AI_ANALYSIS', 'AI Analysis'),
                    ('CAST', 'Cast Columns'),
                    ('RENAME_COLUMN', 'Rename Column'),
                    ('DROP_DUPLICATES', 'Drop Duplicates'),
                    ('REPLACE_VALUES', 'Replace Values'),
                    ('DROP_NULLS', 'Drop Nulls'),
                    ('FILL_NULLS', 'Fill Nulls'),
                    ('FILL_DERIVED', 'Fill Derived'),
                    ('FIX_FORMULA', 'Fix Formula'),
                    ('TRIM_OUTLIERS', 'Trim Outliers'),
                    ('IMPUTE_OUTLIERS', 'Impute Outliers'),
                    ('CAP_OUTLIERS', 'Cap Outliers'),
                    ('TRANSFORM_COLUMN', 'Transform Column'),
                    ('DROP_COLUMNS', 'Drop Columns'),
                    ('ADD_COLUMN', 'Add Column'),
                    ('FILTER_ROWS', 'Filter Rows'),
                    ('CLEAN_STRING', 'Clean String'),
                    ('SCALE_COLUMNS', 'Scale Columns'),
                    ('EXTRACT_DATETIME', 'Extract Datetime'),
                    ('ENCODE_COLUMNS', 'Encode Columns'),
                    ('NORMALIZE_COLUMN_NAMES', 'Normalize Column Names'),
                ],
            ),
        ),
    ]
