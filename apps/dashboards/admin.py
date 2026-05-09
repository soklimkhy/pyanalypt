from django.contrib import admin

from .models import Dashboard, DashboardWidget


class DashboardWidgetInline(admin.TabularInline):
    model  = DashboardWidget
    extra  = 0
    fields = ("title", "chart_type", "grid_row", "grid_col", "grid_width", "grid_height")


@admin.register(Dashboard)
class DashboardAdmin(admin.ModelAdmin):
    list_display    = ("title", "user", "dataset", "created_at", "updated_at")
    list_filter     = ("created_at",)
    search_fields   = ("title", "user__username", "dataset__file_name")
    inlines         = [DashboardWidgetInline]
    readonly_fields = ("created_at", "updated_at")


@admin.register(DashboardWidget)
class DashboardWidgetAdmin(admin.ModelAdmin):
    list_display  = ("title", "chart_type", "dashboard", "grid_row", "grid_col")
    list_filter   = ("chart_type",)
    search_fields = ("title", "dashboard__title")
    readonly_fields = ("chart_config", "created_at", "updated_at")
