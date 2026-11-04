#!/usr/bin/env python3
"""Offline, deterministic quotation calculation. No network or source-file writes."""
import argparse
import copy
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

VERSION = '0.1.0'
CENT = Decimal('0.01')


class InputError(ValueError):
    pass


def number(value):
    if value is None or value == '':
        raise InputError('缺少数值')
    if isinstance(value, bool):
        raise InputError('布尔值不能作为金额或数量')
    try:
        d = Decimal(str(value))
    except InvalidOperation as e:
        raise InputError('数值格式错误') from e
    if not d.is_finite() or d < 0:
        raise InputError('数值须为有限非负数')
    return d


def money(d):
    return format(d.quantize(CENT, rounding=ROUND_HALF_UP), '.2f')


def digest(doc):
    clean = {k: v for k, v in doc.items() if k != 'reviews'}
    return hashlib.sha256(json.dumps(clean, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix(p.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(p)


def calculate(doc):
    if doc.get('schema_version') != '1.0':
        raise InputError('不支持的数据版本')
    project = doc.get('project', {})
    if not all(project.get(k) for k in ('id', 'name', 'revision', 'price_basis')):
        raise InputError('缺少项目编号、名称、版本或含税口径')
    if project['price_basis'] not in ('inclusive', 'exclusive'):
        raise InputError('price_basis须为inclusive或exclusive')
    if project.get('currency', 'CNY') != 'CNY':
        raise InputError('本版仅支持人民币，不能混合币种')
    items = doc.get('items', [])
    if not items:
        raise InputError('项目没有计价项')
    ids = [x.get('id') for x in items]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise InputError('计价项编号为空或重复')
    by_id = {x['id']: x for x in items}
    source_list = [s['id'] for s in doc.get('sources', [])]
    source_ids = set(source_list)
    if len(source_list) != len(source_ids):
        raise InputError('来源编号重复')
    issues, rows, active, groups = [], [], set(), {}

    def issue(code, message, item=None, blocking=True):
        issues.append(dict(code=code, message=message, item=item, blocking=blocking))

    for x in items:
        if x.get('scope') not in ('base', 'optional', 'excluded'):
            raise InputError('未知范围分类：' + x['id'])
        if 'selected' in x and not isinstance(x['selected'], bool):
            raise InputError('selected必须是布尔值：' + x['id'])
        selected = x['scope'] == 'base' or (x['scope'] == 'optional' and x.get('selected', False))
        if x['scope'] == 'excluded' and x.get('selected'):
            raise InputError('排除项不能同时选中：' + x['id'])
        if x.get('frequency', 'once') not in ('once', 'year'):
            raise InputError('本版周期仅支持once或year：' + x['id'])
        if selected:
            active.add(x['id'])
        key = (x.get('bucket', '软件'), x.get('frequency', 'once'))
        if selected:
            groups.setdefault(key, {'subtotal': Decimal(0), 'credit': Decimal(0), 'ids': []})['ids'].append(x['id'])
        method = x.get('method')
        if x.get('included_in') and method != 'included':
            raise InputError('已含归属与独立收费冲突：' + x['id'])
        p = x.get('pricing', {})
        amount, base, factor, cost = None, None, None, None
        error = None
        try:
            if method == 'service_days':
                if p.get('rate_kind') != 'service_price' or p.get('markup') is not None:
                    raise InputError('综合工日价须标为service_price，且不能再叠加加成')
                base, factor = number(p.get('days')), number(p.get('rate'))
            elif method == 'module_price':
                if p.get('rate_kind') != 'module_price' or p.get('markup') is not None:
                    raise InputError('模块售价不能按内部成本再加成')
                base, factor = number(p.get('quantity')), number(p.get('unit_price'))
            elif method == 'cost_plus':
                if p.get('rate_kind') != 'cost':
                    raise InputError('成本加成只接受内部成本')
                components = p.get('components', [])
                if not components or len({c.get('id') for c in components}) != len(components):
                    raise InputError('成本明细缺失或编号重复')
                cost = sum((number(c.get('amount')) for c in components), Decimal(0))
                base, factor = cost, 1 + number(p.get('markup'))
            elif method == 'included':
                if not x.get('included_in'):
                    raise InputError('已含项缺少收费归属')
                if p:
                    raise InputError('已含项不得另外设置价格')
                base, factor = Decimal(0), Decimal(1)
            else:
                raise InputError('计价方式缺失或不受支持')
            amount = (base * factor).quantize(CENT, rounding=ROUND_HALF_UP)
            if selected and amount == 0 and method != 'included' and not x.get('zero_reason'):
                issue('ZERO_REASON', '零价需要说明依据', x['id'])
        except InputError as e:
            error = str(e)
            if selected:
                issue('PRICE_INPUT', error, x['id'])
        if selected and not x.get('source_refs'):
            issue('SOURCE_MISSING', '缺少来源或人工估算依据', x['id'])
        for ref in x.get('source_refs', []):
            if ref not in source_ids:
                issue('SOURCE_UNKNOWN', '来源编号不存在：' + ref, x['id'], selected)
        if selected and amount is not None:
            groups[key]['subtotal'] += amount
        rows.append(dict(id=x['id'], name=x.get('name', x['id']), bucket=key[0], frequency=key[1],
                         scope=x['scope'], selected=selected, method=method,
                         amount=money(amount) if amount is not None else None,
                         factor_a=str(base) if base is not None else None,
                         factor_b=str(factor) if factor is not None else None,
                         cost=money(cost) if cost is not None else None,
                         description=x.get('description', ''), conditions=x.get('conditions', ''),
                         included_in=x.get('included_in', []), feature_ids=x.get('feature_ids', []),
                         source_refs=x.get('source_refs', []), error=error))
    rowmap = {r['id']: r for r in rows}
    # Validate the entire ownership graph, including inactive optional items.
    visiting, visited = set(), set()

    def walk(item_id):
        if item_id in visiting:
            issue('INCLUSION_CYCLE', '已含关系存在循环', item_id)
            return
        if item_id in visited:
            return
        visiting.add(item_id)
        for owner in by_id[item_id].get('included_in', []):
            if owner not in by_id:
                issue('OWNER_UNKNOWN', '收费归属不存在：' + owner, item_id)
            else:
                if item_id in active and owner not in active:
                    issue('OWNER_NOT_SELECTED', '已含项对应收费项未选中：' + owner, item_id)
                walk(owner)
        visiting.remove(item_id)
        visited.add(item_id)
    for i in ids:
        walk(i)
    conditions = doc.get('conditions', {})
    if any(v is not None and not isinstance(v, bool) for v in conditions.values()):
        raise InputError('条件只能为true、false或null')
    relations = doc.get('relations', [])
    relation_ids = [r.get('id') for r in relations]
    if any(not r for r in relation_ids) or len(set(relation_ids)) != len(relation_ids):
        raise InputError('关系编号缺失或重复')
    adjustments, credited_items = [], set()
    for rel in relations:
        kind = rel.get('kind')
        members = rel.get('items', [])
        if not members or len(set(members)) != len(members) or any(i not in by_id for i in members):
            raise InputError('关系项缺失、重复或指向不存在项目：' + rel['id'])
        if kind == 'exclusive':
            if len(active.intersection(members)) > 1:
                issue('EXCLUSIVE', '互斥项同时选中：' + '、'.join(members))
        elif kind == 'requires_any':
            if len(members) != 1:
                raise InputError('依赖关系必须指定一个发起项')
            alternatives = rel.get('any_of', [])
            for a in alternatives:
                if set(a) not in ({'item'}, {'condition'}):
                    raise InputError('依赖替代条件格式错误')
                if 'item' in a and a['item'] not in by_id:
                    raise InputError('依赖的计价项不存在')
            fulfilled = any((a.get('item') in active if 'item' in a else
                             conditions.get(a.get('condition')) is True) for a in alternatives)
            if members[0] in active and not fulfilled:
                issue('DEPENDENCY', '依赖未满足：' + rel.get('description', rel['id']), members[0])
        elif kind == 'overlap_credit':
            if set(members).issubset(active):
                state = conditions.get(rel.get('condition'))
                if state is None:
                    issue('OVERLAP_UNCONFIRMED', '重叠范围尚未确认：' + rel.get('description', rel['id']))
                elif state is True:
                    if credited_items.intersection(members):
                        issue('OVERLAP_DUPLICATE', '同一工作包参与多条扣减，请拆分后核定')
                        continue
                    keys = {(rowmap[i]['bucket'], rowmap[i]['frequency']) for i in members}
                    amounts = [rowmap[i]['amount'] for i in members]
                    if len(keys) != 1 or None in amounts:
                        issue('OVERLAP_INVALID', '扣减跨费用周期/类别或参与项缺价')
                        continue
                    credit = number(rel.get('amount'))
                    if credit > min(number(a) for a in amounts):
                        issue('CREDIT_EXCESS', '共用扣减超过参与项金额')
                        continue
                    key = next(iter(keys))
                    groups[key]['credit'] += credit
                    credited_items.update(members)
                    adjustments.append(dict(id=rel['id'], bucket=key[0], frequency=key[1],
                                            amount=money(-credit), name=rel.get('description', '共用扣减')))
        else:
            raise InputError('未知计费关系：' + str(kind))
    # Every explicitly scoped requirement needs a disposition.
    for req in doc.get('requirements', []):
        mapped = req.get('item_ids', [])
        if req.get('disposition') == 'excluded' and req.get('reason'):
            continue
        if not mapped or any(i not in by_id for i in mapped):
            issue('REQUIREMENT_UNMAPPED', '需求缺少有效计价归属：' + req['id'])
        elif req.get('required') and not any(i in active for i in mapped):
            issue('REQUIREMENT_NOT_SELECTED', '必选需求未纳入当前方案：' + req['id'])
    for q in doc.get('open_questions', []):
        if not q.get('resolved'):
            issue('OPEN_QUESTION', q['question'], blocking=q.get('blocks_price', True))
    tax = None
    if project.get('tax_rate') not in (None, ''):
        tax = number(project['tax_rate'])
        if tax > 1:
            raise InputError('税率应按小数填写，例如0.06')
    if project['price_basis'] == 'exclusive' and tax is None:
        issue('TAX_MISSING', '未税报价缺少税率，无法生成含税总价')
    overrides = doc.get('overrides', [])
    override_map = {}
    for o in overrides:
        key = (o['bucket'], o['frequency'])
        if key not in groups or key in override_map:
            raise InputError('执行价重复或没有对应费用组')
        if not o.get('reason'):
            issue('OVERRIDE_REASON', '执行价缺少调整理由')
        override_map[key] = number(o.get('amount'))
    incomplete = any(i['blocking'] for i in issues)
    totals = []
    for key, g in groups.items():
        estimate = g['subtotal'] - g['credit']
        execution = override_map.get(key, estimate)
        if key in override_map:
            adjustments.append(dict(id='override:' + '|'.join(key), bucket=key[0], frequency=key[1],
                                    amount=money(execution-estimate), name='商务调整'))
        if project['price_basis'] == 'inclusive':
            gross = execution
            net = (gross / (1 + tax)).quantize(CENT, rounding=ROUND_HALF_UP) if tax is not None else None
            tax_amount = gross-net if net is not None else None
        else:
            net = execution
            tax_amount = (net*tax).quantize(CENT, rounding=ROUND_HALF_UP) if tax is not None else None
            gross = net+tax_amount if tax_amount is not None else None
        totals.append(dict(bucket=key[0], frequency=key[1], known_subtotal=money(g['subtotal']),
                           credit=money(g['credit']), estimate=money(estimate) if not incomplete else None,
                           execution=money(execution) if not incomplete else None,
                           gross=money(gross) if gross is not None and not incomplete else None,
                           net=money(net) if net is not None and not incomplete else None,
                           tax=money(tax_amount) if tax_amount is not None and not incomplete else None))
    fingerprint = digest(doc)
    reviews = {stage: '有效' if any(r.get('stage') == stage and r.get('input_hash') == fingerprint
                                   and r.get('reviewer') and r.get('date') for r in doc.get('reviews', []))
               else '待复核' for stage in ('scope', 'technical', 'commercial')}
    return dict(engine_version=VERSION, input_hash=fingerprint, rule_version=doc.get('rule_version'),
                project=copy.deepcopy(project), status='待补充' if incomplete else '可审阅草稿',
                reviews=reviews, items=rows, adjustments=adjustments, totals=totals, issues=issues)


def customer_view(result):
    # Whitelist only: never copy the internal input/result then delete fields.
    return dict(project={k: result['project'].get(k) for k in ('id', 'name', 'revision', 'currency', 'price_basis', 'tax_rate', 'date')},
                status=result['status'], input_hash=result['input_hash'],
                items=[{k: r[k] for k in ('id', 'name', 'bucket', 'frequency', 'scope', 'selected', 'amount',
                                          'description', 'conditions', 'included_in')} for r in result['items']],
                adjustments=result['adjustments'],
                totals=[{k: t[k] for k in ('bucket', 'frequency', 'known_subtotal', 'gross', 'net', 'tax')} for t in result['totals']])


def diff(old, new):
    changes = []
    def visit(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                visit(a.get(k), b.get(k), path + '/' + k)
        elif a != b:
            changes.append(dict(field=path, before=a, after=b))
    visit(old, new, '')
    return dict(changed=bool(changes), review_invalidated=digest(old) != digest(new), changes=changes)


def main():
    p = argparse.ArgumentParser(description='软件报价助手计算工具')
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('calculate'); c.add_argument('input'); c.add_argument('--output', required=True)
    d = sub.add_parser('diff'); d.add_argument('old'); d.add_argument('new'); d.add_argument('--output', required=True)
    args = p.parse_args()
    if args.command == 'calculate':
        out = Path(args.output)
        result = calculate(read(args.input))
        save(out/'internal.json', result)
        save(out/'customer.json', customer_view(result))
        save(out/'input-snapshot.json', read(args.input))
        print(json.dumps({k: result[k] for k in ('status', 'totals', 'reviews')}, ensure_ascii=False))
    else:
        save(args.output, diff(read(args.old), read(args.new)))


if __name__ == '__main__':
    main()
