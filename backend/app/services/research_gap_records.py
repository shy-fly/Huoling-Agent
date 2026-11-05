"""Adapt verified group-table rows to the coverage record schema."""
import re

_HEADER = re.compile(r"(?P<field>.+?)\s*\((?P<unit>[^()]+)\)$")
_VALUE = re.compile(r"(?P<center>[+-]?\d+(?:\.\d+)?)(?:\s*±\s*\d+(?:\.\d+)?)?")


def collectGroupRecords(result: dict) -> list[dict]:
    records = []
    for sourceId, tables in result.get("groupTables", {}).items():
        source = result["papers"][sourceId][0]
        for table in tables:
            rows = {}
            for cell in table["records"]:
                group = cell["group"]
                row = rows.setdefault(cell["row"], {
                    "id": f'{sourceId}:{table["page"]}:group:{table["tableIndex"]}:{cell["row"]}',
                    "sourceId": sourceId, "source": source["source"], "collection": source["collection"],
                    "page": table["page"], "group": group, "fields": {"group": [group, ""]},
                    "rawCells": {},
                })
                header = _HEADER.fullmatch(cell["header"])
                if header:
                    field, unit = header["field"].strip(), header["unit"].strip()
                else:
                    field, unit = cell["header"].strip(), ""
                if field == "group":
                    continue
                raw = cell["verifiedValue"]
                parsed = _VALUE.fullmatch(raw or "")
                value = [parsed["center"], unit] if parsed else None
                current = row["fields"].setdefault(field, value)
                if current != value:
                    row["fields"][field] = None
                row["rawCells"][field] = raw or cell["rawCell"]
            records.extend(rows.values())
    return records

