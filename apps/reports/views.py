import logging

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Report, ReportItem
from .pdf import generate_report_pdf
from .serializers import ReportItemSerializer, ReportListSerializer, ReportSerializer

logger = logging.getLogger(__name__)

_MAX_ITEMS_PER_REPORT = 50


class ReportViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        reports = Report.objects.filter(user=request.user).prefetch_related("items")
        return Response(ReportListSerializer(reports, many=True).data)

    def create(self, request):
        serializer = ReportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        report = get_object_or_404(Report, pk=pk, user=request.user)
        return Response(ReportSerializer(report).data)

    def partial_update(self, request, pk=None):
        report = get_object_or_404(Report, pk=pk, user=request.user)
        serializer = ReportSerializer(report, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, pk=None):
        report = get_object_or_404(Report, pk=pk, user=request.user)
        report.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        report = get_object_or_404(Report, pk=pk, user=request.user)
        try:
            pdf_buffer = generate_report_pdf(report)
        except Exception:
            logger.exception("PDF generation failed for report %s", pk)
            return Response({"detail": "Failed to generate PDF."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in report.title).strip()
        filename = f"{safe_title or 'report'}.pdf"
        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class ReportItemViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _get_report(self, request, report_pk):
        return get_object_or_404(Report, pk=report_pk, user=request.user)

    def create(self, request, report_pk=None):
        report = self._get_report(request, report_pk)

        if report.items.count() >= _MAX_ITEMS_PER_REPORT:
            return Response(
                {"detail": f"A report cannot exceed {_MAX_ITEMS_PER_REPORT} items."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = ReportItemSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save(report=report)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, report_pk=None, pk=None):
        report = self._get_report(request, report_pk)
        item = get_object_or_404(ReportItem, pk=pk, report=report)
        serializer = ReportItemSerializer(item, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)

    def destroy(self, request, report_pk=None, pk=None):
        report = self._get_report(request, report_pk)
        item = get_object_or_404(ReportItem, pk=pk, report=report)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
