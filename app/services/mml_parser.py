import re
from typing import Any


class MMLAutoParser:
    @staticmethod
    def detect_format(raw_report: str) -> str:
        lines = [line.strip() for line in raw_report.split("\n") if line.strip()]

        divider_idx = -1
        for index, line in enumerate(lines):
            if line.startswith("---") and "---    END" not in line:
                divider_idx = index
                break

        start_search_idx = divider_idx + 1 if divider_idx != -1 else 4
        for line in lines[start_search_idx:]:
            if line.startswith("(Number of results") or line.startswith("---"):
                continue
            if "=" in line and not line.startswith("RETCODE"):
                return "vertical"

        return "horizontal"

    @classmethod
    def parse(
        cls,
        raw_report: str,
        flatten_lists: bool = True,
        selected_columns: list[str] | None = None,
    ) -> dict[str, Any]:
        if not raw_report.strip().endswith("---    END"):
            raise ValueError("Error: Reporte MML incompleto (No se detectó '---    END').")

        header_match = re.search(
            r"\+\+\+\s+(\S+)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",
            raw_report,
        )
        ne_name = header_match.group(1) if header_match else "Unknown_NE"
        timestamp = header_match.group(2) if header_match else None

        retcode_match = re.search(r"RETCODE\s*=\s*(\d+)", raw_report)
        ret_code = int(retcode_match.group(1)) if retcode_match else -1
        if ret_code != 0:
            return {
                "neName": ne_name,
                "formatDetected": "unknown",
                "retCode": ret_code,
                "timestamp": timestamp,
                "records": [],
            }

        report_format = cls.detect_format(raw_report)
        records = (
            cls._parse_horizontal(raw_report, selected_columns)
            if report_format == "horizontal"
            else cls._parse_vertical(raw_report, flatten_lists)
        )
        return {
            "neName": ne_name,
            "formatDetected": report_format,
            "retCode": ret_code,
            "timestamp": timestamp,
            "records": records,
        }

    @staticmethod
    def _parse_horizontal(raw_report: str, selected_columns: list[str] | None) -> list[dict[str, str | None]]:
        lines = [line.strip() for line in raw_report.split("\n") if line.strip()]
        divider_idx = next(
            index for index, line in enumerate(lines)
            if line.startswith("---") and "---    END" not in line
        )
        raw_headers = re.split(r"\s{2,}", lines[divider_idx + 1])
        headers_to_map = [header for header in raw_headers if header in selected_columns] if selected_columns else raw_headers

        records: list[dict[str, str | None]] = []
        for line in lines[divider_idx + 2:]:
            if line.startswith("(Number of results") or line.startswith("---"):
                break
            row_values = re.split(r"\s{2,}", line)
            record: dict[str, str | None] = {}
            for header in headers_to_map:
                original_index = raw_headers.index(header)
                value = row_values[original_index] if original_index < len(row_values) else None
                record[header] = None if value == "NULL" else value
            records.append(record)
        return records

    @staticmethod
    def _parse_vertical(raw_report: str, flatten_lists: bool) -> list[dict[str, Any]]:
        lines = [line.rstrip() for line in raw_report.split("\n")]
        divider_idx = -1
        for index, line in enumerate(lines):
            if line.strip().startswith("---") and "---    END" not in line:
                divider_idx = index
                break
        if divider_idx == -1:
            divider_idx = next(index for index, line in enumerate(lines) if "=" in line and index > 3) - 1

        records: list[dict[str, Any]] = []
        current_record: dict[str, Any] = {}
        last_key: str | None = None
        for line in lines[divider_idx + 1:]:
            stripped = line.strip()
            if stripped.startswith("(Number of results") or stripped.startswith("---    END"):
                break
            if not stripped:
                if current_record:
                    records.append(current_record)
                    current_record = {}
                    last_key = None
                continue

            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = None if value.strip() == "NULL" else value.strip()
                if not key:
                    if last_key and last_key in current_record and value is not None:
                        existing = current_record[last_key]
                        if isinstance(existing, list):
                            existing.append(value)
                        elif existing is not None:
                            current_record[last_key] = [existing, value]
                        else:
                            current_record[last_key] = value
                else:
                    current_record[key] = value
                    last_key = key

        if current_record:
            records.append(current_record)

        if flatten_lists:
            for record in records:
                for key, value in record.items():
                    if isinstance(value, list):
                        record[key] = ", ".join(str(item) for item in value)
        return records