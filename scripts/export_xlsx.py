#!/usr/bin/env python3
"""Minimal XLSX writer using only Python standard library. All cells are text."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
from quote import calculate, customer_view, read


def cell_text(value):
    if value is None:
        return ''
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def column_name(index):
    result = ''
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def write_xlsx(path, sheets):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    rel = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    types = ['<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>']
    workbook, relationships, worksheets = [], [], []
    for i, (name, rows) in enumerate(sheets, 1):
        workbook.append(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>')
        relationships.append(f'<Relationship Id="rId{i}" Type="{rel}/worksheet" Target="worksheets/sheet{i}.xml"/>')
        types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        data = []
        for r, row in enumerate(rows, 1):
            cells = []
            for c, value in enumerate(row, 1):
                # Explicit inline strings prevent formula execution, including =, +, -, @.
                text = ''.join(ch for ch in cell_text(value) if ch in '\t\n\r' or 32 <= ord(ch) <= 0xD7FF or 0xE000 <= ord(ch) <= 0xFFFD or 0x10000 <= ord(ch) <= 0x10FFFF)
                cells.append(f'<c r="{column_name(c)}{r}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>')
            data.append(f'<row r="{r}">{"".join(cells)}</row>')
        worksheets.append(f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{ns}"><sheetData>{"".join(data)}</sheetData></worksheet>')
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+''.join(types)+'</Types>')
        z.writestr('_rels/.rels', f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="{rel}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="{rel}"><sheets>{"".join(workbook)}</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(relationships)+'</Relationships>')
        for i, xml in enumerate(worksheets, 1):
            z.writestr(f'xl/worksheets/sheet{i}.xml', xml)


def table(rows, keys):
    return [keys] + [[r.get(k) for k in keys] for r in rows]


def export(doc, destination):
    result = calculate(doc)
    customer = customer_view(result)
    out = Path(destination)
    summary = [['状态', customer['status']], ['说明', '工作稿；非审批或合同。金额均为计算值，范围与文字需人工复核。']]
    summary += [[k, v] for k, v in customer['project'].items()]
    public_sheets = [('项目说明', summary),
                     ('报价明细', table(customer['items'], ['id','name','bucket','frequency','scope','selected','amount','description','conditions','included_in'])),
                     ('费用汇总', table(customer['totals'], ['bucket','frequency','known_subtotal','gross','net','tax'])),
                     ('商务调整', table(customer['adjustments'], ['id','bucket','frequency','amount','name']))]
    write_xlsx(out/'customer.xlsx', public_sheets)
    write_xlsx(out/'internal.xlsx', [
        ('内部说明', [['仅内部使用', '含成本与计算因子，不可发给客户'], ['状态',result['status']]]),
        ('内部测算', table(result['items'], ['id','name','method','amount','factor_a','factor_b','cost','source_refs','error'])),
        ('内部汇总', table(result['totals'], ['bucket','frequency','known_subtotal','credit','estimate','execution','gross','net','tax'])),
        ('问题', table(result['issues'], ['code','message','item','blocking']))])
    return out/'customer.xlsx', out/'internal.xlsx'


def main():
    p = argparse.ArgumentParser(description='导出独立的客户/内部 XLSX 工作稿')
    p.add_argument('input'); p.add_argument('--output', required=True)
    a = p.parse_args()
    for path in export(read(a.input), a.output):
        print(path)


if __name__ == '__main__':
    main()
