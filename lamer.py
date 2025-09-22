import streamlit as st
import pandas as pd
import json
import re
from datetime import datetime, timedelta
import plotly.graph_objects as go
from pathlib import Path
import time 

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="La Mer",
    page_icon="🌊",
    layout="wide"
)

# ==================== 数据文件路径 ====================
DATA_DIR = Path("lamer_data")
DATA_DIR.mkdir(exist_ok=True)

# CSV文件
INVENTORY_CSV = DATA_DIR / "inventory.csv"
HISTORY_CSV = DATA_DIR / "history.csv"
LOST_CSV = DATA_DIR / "lost.csv"
SOLD_CSV = DATA_DIR / "sold.csv"
EXCHANGE_RATE_CSV = DATA_DIR / "exchange_rates.csv"

# JSON文件
PRODUCTS_JSON = DATA_DIR / "products_global.json"
CATEGORIES_JSON = DATA_DIR / "categories.json"
ACCOUNTS_JSON = DATA_DIR / "accounts.json"
SUBSCRIPTIONS_JSON = DATA_DIR / "subscriptions.json"
DEPOSITS_JSON = DATA_DIR / "deposits.json"

BASE_CURRENCY = 'EUR'

# ==================== 工具函数 ====================
def load_csv(file_path, columns):
    """加载CSV文件"""
    if file_path.exists():
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            for col in columns:
                if col not in df.columns:
                    df[col] = None
            return df
        except:
            return pd.DataFrame(columns=columns)
    return pd.DataFrame(columns=columns)

def save_csv(df, file_path):
    """保存CSV文件"""
    df.to_csv(file_path, index=False, encoding='utf-8')

def load_json(file_path, default=None):
    """加载JSON文件"""
    if default is None:
        default = {}
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(data, file_path):
    """保存JSON文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def init_exchange_rates():
    """初始化汇率快照"""
    if not EXCHANGE_RATE_CSV.exists():
        rates = pd.DataFrame({
            'month': ['2025-09'],
            'EUR': [1.0],
            'CNY': [7.8],
            'USD': [1.1],
            'JPY': [150.0]
        })
        save_csv(rates, EXCHANGE_RATE_CSV)
    return pd.read_csv(EXCHANGE_RATE_CSV)

def get_exchange_rate(currency, date_str):
    """获取指定日期的汇率"""
    rates_df = pd.read_csv(EXCHANGE_RATE_CSV)
    month = date_str[:7]
    rate_row = rates_df[rates_df['month'] == month]
    
    if rate_row.empty:
        rate_row = rates_df.iloc[-1]
        rate = float(rate_row[currency])
    else:
        rate = float(rate_row[currency].values[0])
    
    return rate

def to_eur(amount, currency, purchase_date):
    """转换为EUR基准"""
    if currency == BASE_CURRENCY:
        return amount
    rate = get_exchange_rate(currency, purchase_date)
    return amount / rate

def generate_product_id(name):
    """生成商品ID"""
    date = datetime.now().strftime('%y%m%d')
    random = str(hash(name + str(datetime.now())) % 10000).zfill(4)
    simple_name = ''.join(e for e in name if e.isalnum())[:6].lower()
    return f"{date}{random}_{simple_name}"

def expand_quick_input(text, products_db, categories_db, accounts_db):
    """展开快速输入语法"""
    lines = text.split('\n')
    expanded_lines = []
    
    for line in lines:
        expanded_line = line
        
        # $ 模式 - 账户
        # 改进后的 $ 模式
        if '$' in line and accounts_db:
            import re
            # 找到所有 $xxx 模式
            for match in re.finditer(r'\$(\w+)', line):
                hint = match.group(1).lower()
                # 前缀匹配
                for account in accounts_db:
                    if account.lower().startswith(hint):
                        expanded_line = line.replace(f'${match.group(1)}', account)
                        break
        
        # # 模式 - 类型
        if line.startswith('## #'):
            category_hint = line[4:].strip()
            for cat in categories_db:
                if category_hint.lower() in cat.lower():
                    expanded_line = f'## {cat}'
                    break
        
        # ? 模式 - 商品
        if line.strip().startswith('?'):
            product_hint = line.strip()[1:].strip()
            for product_name, product_info in products_db.items():
                if product_hint.lower() in product_name.lower():
                    expanded_line = f"{product_name} >> {product_info['standardPrice']}"
                    break
        
        expanded_lines.append(expanded_line)
    
    return '\n'.join(expanded_lines)

def parse_input_text(text, products_db, deposits_db):
    """解析入库文本"""
    lines = text.strip().split('\n')
    metadata = {}
    items = []
    current_category = ''
    in_metadata = False
    deposit_returns = []
    
    for line in lines:
        line = line.strip()
        
        if line == '---':
            in_metadata = not in_metadata
            continue
            
        if in_metadata:
            if '：' in line:
                key, value = line.split('：', 1)
                metadata[key.strip()] = value.strip()
        elif line.startswith('## '):
            current_category = line[3:].strip()
        elif line.startswith('Pfand') and '<<' in line:
            # 押金返还
            match_parts = line.split('<<')
            left_part = match_parts[0].strip()
            amount = float(match_parts[1].strip())
            
            count_match = re.search(r'\((\d+)\)', left_part)
            if count_match:
                count = int(count_match.group(1))
                deposit_returns.append({
                    'count': count,
                    'amount': amount,
                    'date': metadata.get('日期', datetime.now().strftime('%Y-%m-%d'))
                })
        elif '>>' in line:
            parts = line.split('>>')
            left_part = parts[0].strip()
            right_part = parts[1].strip()
            
            invoice_name = ''
            product_name = left_part
            if '::' in left_part:
                invoice_parts = left_part.split('::')
                invoice_name = invoice_parts[0].strip()
                product_name = invoice_parts[1].strip()
                if metadata.get('入金'):
                    invoice_name = f"{metadata['入金']}_{invoice_name}"
            
            standard_price = 0
            actual_price = 0
            
            if '::' in right_part:
                prices = right_part.split('::')
                standard_price = float(prices[0].strip())
                actual_price = float(prices[1].strip())
            else:
                price = float(right_part.strip())
                standard_price = price
                actual_price = price
            
            discount = standard_price - actual_price
            currency = metadata.get('币种', 'EUR')
            purchase_date = metadata.get('日期', datetime.now().strftime('%Y-%m-%d'))
            purchase_rate = get_exchange_rate(currency, purchase_date)
            
            item = {
                'id': generate_product_id(product_name),
                'name': product_name,
                'category': current_category,
                'actualPrice': actual_price,
                'standardPrice': standard_price,
                'currency': currency,
                'purchaseDate': purchase_date,
                'source': metadata.get('入金', ''),
                'account': metadata.get('出金', ''),
                'invoiceName': invoice_name,
                'discount': discount,
                'inTransit': False,
                'purchaseRate': purchase_rate
            }
            
            items.append(item)
            
            # 检查是否为Pfand
            if 'pfand' in product_name.lower() or current_category.lower() == 'pfand':
                deposits_db[product_name] = deposits_db.get(product_name, 0) + 1
            
            if product_name not in products_db:
                products_db[product_name] = {
                    'name': product_name,
                    'standardPrice': standard_price,
                    'currency': currency,
                    'category': current_category,
                    'purchaseCount': 0,
                    'buyout': True
                }
    
    return items, products_db, deposit_returns

def parse_subscription_input(text):
    """解析订阅输入"""
    lines = text.strip().split('\n')
    metadata = {}
    subs = []
    in_metadata = False
    
    for line in lines:
        line = line.strip()
        
        if line == '---':
            in_metadata = not in_metadata
            continue
        
        if in_metadata:
            if '：' in line:
                key, value = line.split('：', 1)
                metadata[key.strip()] = value.strip()
        elif line.startswith('订阅:'):
            parts = line.split(' ', 1)
            sub_config = parts[0].split(':')
            
            if len(sub_config) >= 3 and '>>' in line:
                period = sub_config[1]
                date_str = sub_config[2]
                
                product_line = parts[1] if len(parts) > 1 else ''
                if '>>' in product_line:
                    prod_parts = product_line.split('>>')
                    product_name = prod_parts[0].strip()
                    price = float(prod_parts[1].strip())
                    
                    today = datetime.now().date()
                    
                    if period == 'M':
                        day = int(date_str)
                        next_date = today.replace(day=day)
                        if next_date <= today:
                            next_month = today.replace(day=1) + timedelta(days=32)
                            next_date = next_month.replace(day=day)
                    else:  # Y
                        month = int(date_str[:2])
                        day = int(date_str[2:])
                        next_date = today.replace(month=month, day=day)
                        if next_date <= today:
                            next_date = next_date.replace(year=today.year + 1)
                    
                    subs.append({
                        'name': product_name,
                        'price': price,
                        'period': period,
                        'day': date_str,
                        'nextDate': next_date.strftime('%Y-%m-%d'),
                        'currency': metadata.get('币种', 'EUR'),
                        'source': metadata.get('入金', ''),
                        'account': metadata.get('出金', ''),
                        'category': metadata.get('类型', '订阅服务')
                    })
    
    return subs

def check_subscriptions(subscriptions_db, inventory_df, history_df, deposits_db):
    """检查并处理订阅续费"""
    today = datetime.now().date()
    renewed = []
    
    for sub_name, sub_info in subscriptions_db.items():
        next_date = datetime.strptime(sub_info['nextDate'], '%Y-%m-%d').date()
        
        if today >= next_date:
            # 自动续费
            item = {
                'id': generate_product_id(sub_name),
                'name': sub_name,
                'category': sub_info['category'],
                'actualPrice': sub_info['price'],
                'standardPrice': sub_info['price'],
                'currency': sub_info['currency'],
                'purchaseDate': today.strftime('%Y-%m-%d'),
                'source': sub_info['source'],
                'account': sub_info['account'],
                'invoiceName': f"订阅_{sub_name}",
                'discount': 0,
                'inTransit': False,
                'purchaseRate': get_exchange_rate(sub_info['currency'], today.strftime('%Y-%m-%d'))
            }
            
            inventory_df = pd.concat([inventory_df, pd.DataFrame([item])], ignore_index=True)
            
            # 旧订阅出库
            old_items = inventory_df[
                (inventory_df['name'] == sub_name) & 
                (inventory_df['id'] != item['id'])
            ]
            
            for _, old_item in old_items.iterrows():
                old_dict = old_item.to_dict()
                old_dict['checkoutDate'] = today.strftime('%Y-%m-%d')
                old_dict['utilization'] = 100
                old_dict['checkoutMode'] = 'subscription_auto'
                old_dict['daysInService'] = (today - datetime.strptime(old_item['purchaseDate'], '%Y-%m-%d').date()).days
                
                history_df = pd.concat([history_df, pd.DataFrame([old_dict])], ignore_index=True)
                inventory_df = inventory_df[inventory_df['id'] != old_item['id']]
            
            # 更新下次续费日期
            if sub_info['period'] == 'M':
                day = int(sub_info['day'])
                next_month = next_date.replace(day=1) + timedelta(days=32)
                subscriptions_db[sub_name]['nextDate'] = next_month.replace(day=day).strftime('%Y-%m-%d')
            elif sub_info['period'] == 'Y':
                month = int(sub_info['day'][:2])
                day = int(sub_info['day'][2:])
                subscriptions_db[sub_name]['nextDate'] = next_date.replace(year=next_date.year + 1, month=month, day=day).strftime('%Y-%m-%d')
            
            renewed.append(sub_name)
    
    return inventory_df, history_df, subscriptions_db, renewed

# ==================== 初始化数据 ====================
# CSV列定义
inv_cols = ['id', 'name', 'category', 'actualPrice', 'standardPrice', 'currency', 
            'purchaseDate', 'source', 'account', 'invoiceName', 'discount', 'inTransit', 'purchaseRate']
hist_cols = inv_cols + ['checkoutDate', 'utilization', 'daysInService', 'checkoutMode']
lost_cols = inv_cols + ['lostDate']
sold_cols = hist_cols + ['sellPrice', 'sellAccount']

# 加载数据
inventory_df = load_csv(INVENTORY_CSV, inv_cols)
history_df = load_csv(HISTORY_CSV, hist_cols)
lost_df = load_csv(LOST_CSV, lost_cols)
sold_df = load_csv(SOLD_CSV, sold_cols)

products_db = load_json(PRODUCTS_JSON, {})
categories_db = load_json(CATEGORIES_JSON, ['水果', '谷物', '饮料', '日用品', 'Pfand'])
accounts_db = load_json(ACCOUNTS_JSON, [])
subscriptions_db = load_json(SUBSCRIPTIONS_JSON, {})
deposits_db = load_json(DEPOSITS_JSON, {})

exchange_rates_df = init_exchange_rates()

# 检查订阅续费
inventory_df, history_df, subscriptions_db, renewed_subs = check_subscriptions(
    subscriptions_db, inventory_df, history_df, deposits_db
)

if renewed_subs:
    save_csv(inventory_df, INVENTORY_CSV)
    save_csv(history_df, HISTORY_CSV)
    save_json(subscriptions_db, SUBSCRIPTIONS_JSON)

# ==================== UI界面 ====================
st.sidebar.title("🌊 La Mer v1.31")
st.sidebar.caption("A pilot project of Spar!")
page = st.sidebar.radio("导航", ["入库", "检视", "遗失", "订阅管理", "报表", "操作指南"])

if renewed_subs:
    st.sidebar.success(f"🔄 自动续费: {', '.join(renewed_subs)}")

# ==================== 入库页面 ====================
if page == "入库":
    st.header("📦 货物入库")
    
    with st.expander("📝 快速输入指南"):
        st.markdown("""
        **基本格式：**
        - 商品入库：`商品名 >> 价格`
        - 优惠价格：`商品名 >> 原价 :: 实付`
        
        **押金处理：**
        - 购买带押金：在 `Pfand` 分类下添加
        - 返还押金：`Pfand (数量) << 退款`
        
        **快速输入：**
        - `?商品名` 自动补全
        - `#类型` 快速分类
        - `$账户` 快速账户
        """)
    
    input_text = st.text_area(
        "输入货物信息",
        value=f"""---
日期：{datetime.now().strftime('%Y-%m-%d')}
入金：
出金：
币种：EUR
---

## 
""",
        height=400
    )
    
    processed_text = expand_quick_input(input_text, products_db, categories_db, accounts_db)
    
    if processed_text != input_text:
        with st.expander("查看处理后的文本"):
            st.code(processed_text)
    
    if st.button("✅ 确认入库", type="primary"):
        new_items, products_db, deposit_returns = parse_input_text(processed_text, products_db, deposits_db)
        
        # 处理押金返还
        if deposit_returns:
            for ret in deposit_returns:
                pfand_items = inventory_df[
                    (inventory_df['name'].str.contains('Pfand', case=False, na=False)) |
                    (inventory_df['category'] == 'Pfand')
                ].head(ret['count'])
                
                for _, pfand_item in pfand_items.iterrows():
                    item_dict = pfand_item.to_dict()
                    item_dict['checkoutDate'] = ret['date']
                    item_dict['utilization'] = 100
                    item_dict['checkoutMode'] = 'pfand_return'
                    item_dict['daysInService'] = (datetime.strptime(ret['date'], '%Y-%m-%d') - 
                                                   datetime.strptime(pfand_item['purchaseDate'], '%Y-%m-%d')).days
                    
                    history_df = pd.concat([history_df, pd.DataFrame([item_dict])], ignore_index=True)
                    inventory_df = inventory_df[inventory_df['id'] != pfand_item['id']]
                    
                    if pfand_item['name'] in deposits_db:
                        deposits_db[pfand_item['name']] = max(0, deposits_db[pfand_item['name']] - 1)
        
        if new_items:
            new_df = pd.DataFrame(new_items)
            inventory_df = pd.concat([inventory_df, new_df], ignore_index=True)
            save_csv(inventory_df, INVENTORY_CSV)
            
            currencies = {}
            for item in new_items:
                curr = item['currency']
                currencies[curr] = currencies.get(curr, 0) + item['actualPrice']
                
                if item['name'] in products_db:
                    products_db[item['name']]['purchaseCount'] += 1
                
                if item['source'] and item['source'] not in accounts_db:
                    accounts_db.append(item['source'])
                if item['account'] and item['account'] not in accounts_db:
                    accounts_db.append(item['account'])
                
                if item['category'] and item['category'] not in categories_db:
                    categories_db.append(item['category'])
            
            save_json(products_db, PRODUCTS_JSON)
            save_json(categories_db, CATEGORIES_JSON)
            save_json(accounts_db, ACCOUNTS_JSON)
            save_json(deposits_db, DEPOSITS_JSON)
            save_csv(history_df, HISTORY_CSV)
            
            currency_summary = ", ".join([f"{v:.2f} {k}" for k, v in currencies.items()])
            success_msg = f"✅ 入库成功！共 {len(new_items)} 件商品"
            time.sleep(1)  # 暂停1秒让用户看到消息
            if currencies:
                success_msg += f"，总计 {currency_summary}"
            if deposit_returns:
                success_msg += f"\n♻️ 返还 {sum([r['count'] for r in deposit_returns])} 个Pfand"
            
            st.success(success_msg)
            
            with st.expander("📋 查看入库明细"):
                for item in new_items:
                    st.write(f"• {item['name']} - {item['actualPrice']} {item['currency']} ({item['category']})")
            
            st.rerun()
        elif deposit_returns:
            save_json(deposits_db, DEPOSITS_JSON)
            save_csv(inventory_df, INVENTORY_CSV)
            save_csv(history_df, HISTORY_CSV)
            st.success(f"♻️ 成功返还 {sum([r['count'] for r in deposit_returns])} 个Pfand")
            st.rerun()
        else:
            st.error("❌ 没有解析到商品")

# ==================== 检视页面 ====================
elif page == "检视":
    st.header("👁️ 货物检视")
    
    if not inventory_df.empty:
        inventory_df['eurValue'] = inventory_df.apply(
            lambda row: to_eur(row['actualPrice'], row['currency'], row['purchaseDate']),
            axis=1
        )
        
        col1, col2 = st.columns([1, 4])
        
        with col1:
            filter_cat = st.selectbox("类型", ["全部"] + categories_db)
            sort_by = st.radio("排序", ["日期", "价值(EUR)"])
        
        filtered_df = inventory_df.copy()
        if filter_cat != "全部":
            filtered_df = filtered_df[filtered_df['category'] == filter_cat]
        
        if sort_by == "价值(EUR)":
            filtered_df = filtered_df.sort_values('eurValue', ascending=False)
        else:
            filtered_df = filtered_df.sort_values('purchaseDate', ascending=False)
        
        # 显示表格
        display_df = filtered_df[['name', 'category', 'purchaseDate', 'actualPrice', 'currency', 'eurValue']].copy()
        display_df['eurValue'] = display_df['eurValue'].round(2)
        
        # 订阅服务标识
        def format_name(row):
            name = row['name']
            if name in subscriptions_db:
                sub_info = subscriptions_db[name]
                period_mark = 'M' if sub_info['period'] == 'M' else 'Y'
                date_str = sub_info['day']
                return f"{name} ({period_mark}{date_str})"
            return name
        
        display_df['商品名称'] = filtered_df.apply(format_name, axis=1)
        display_df = display_df[['商品名称', 'category', 'purchaseDate', 'actualPrice', 'currency', 'eurValue']]
        
        st.dataframe(display_df, hide_index=True, use_container_width=True)
        
        # 出库操作
        st.subheader("📤 出库操作")
        
        selected_items = st.multiselect(
            "选择商品",
            options=filtered_df['id'].tolist(),
            format_func=lambda x: filtered_df[filtered_df['id'] == x]['name'].values[0]
        )
        
        if selected_items:
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.write("**通常出库**")
                utilization = st.slider("利用率%", 0, 100, 100)
                if st.button("确认"):
                    for item_id in selected_items:
                        item = inventory_df[inventory_df['id'] == item_id].iloc[0].to_dict()
                        item['checkoutDate'] = datetime.now().strftime('%Y-%m-%d')
                        item['utilization'] = utilization
                        item['checkoutMode'] = 'normal'
                        item['daysInService'] = (datetime.now() - datetime.strptime(item['purchaseDate'], '%Y-%m-%d')).days
                        
                        history_df = pd.concat([history_df, pd.DataFrame([item])], ignore_index=True)
                        inventory_df = inventory_df[inventory_df['id'] != item_id]
                    
                    save_csv(inventory_df, INVENTORY_CSV)
                    save_csv(history_df, HISTORY_CSV)
                    st.success("✅ 出库成功")
                    st.rerun()
            
            with col2:
                st.write("**遗失**")
                if st.button("标记遗失"):
                    for item_id in selected_items:
                        item = inventory_df[inventory_df['id'] == item_id].iloc[0].to_dict()
                        item['lostDate'] = datetime.now().strftime('%Y-%m-%d')
                        
                        lost_df = pd.concat([lost_df, pd.DataFrame([item])], ignore_index=True)
                        inventory_df = inventory_df[inventory_df['id'] != item_id]
                    
                    save_csv(inventory_df, INVENTORY_CSV)
                    save_csv(lost_df, LOST_CSV)
                    st.warning("⚠️ 已标记遗失")
                    st.rerun()
            
            with col3:
                st.write("**出售**")
                sell_price = st.number_input("售价", 0.0, step=0.1)
                if accounts_db:
                    sell_account = st.selectbox("账户", accounts_db)
                else:
                    sell_account = st.text_input("账户")
                
                if st.button("确认出售"):
                    for item_id in selected_items:
                        item = inventory_df[inventory_df['id'] == item_id].iloc[0].to_dict()
                        item['checkoutDate'] = datetime.now().strftime('%Y-%m-%d')
                        item['checkoutMode'] = 'sell'
                        item['sellPrice'] = sell_price
                        item['sellAccount'] = sell_account
                        item['daysInService'] = (datetime.now() - datetime.strptime(item['purchaseDate'], '%Y-%m-%d')).days
                        
                        sold_df = pd.concat([sold_df, pd.DataFrame([item])], ignore_index=True)
                        inventory_df = inventory_df[inventory_df['id'] != item_id]
                    
                    save_csv(inventory_df, INVENTORY_CSV)
                    save_csv(sold_df, SOLD_CSV)
                    st.success("💰 出售成功")
                    st.rerun()
            
            with col4:
                st.write("**删除 / AA款清账**")
                st.caption("删除误操作或结清AA款项，相关记录不会计入支出趋势图。")
                if st.button("🗑️ 删除"):
                    for item_id in selected_items:
                        inventory_df = inventory_df[inventory_df['id'] != item_id]
                    
                    save_csv(inventory_df, INVENTORY_CSV)
                    st.info(f"🗑️ 已删除 {len(selected_items)} 条")
                    st.rerun()
    else:
        st.info("暂无库存")

# ==================== 遗失页面 ====================
elif page == "遗失":
    st.header("❌ 遗失物品")
    
    if not lost_df.empty:
        st.dataframe(lost_df[['name', 'lostDate', 'actualPrice']], hide_index=True)
        
        selected_lost = st.multiselect(
            "找回",
            lost_df['id'].tolist(),
            format_func=lambda x: lost_df[lost_df['id'] == x]['name'].values[0]
        )
        
        if selected_lost and st.button("🔄 确认找回"):
            for item_id in selected_lost:
                item = lost_df[lost_df['id'] == item_id].iloc[0].to_dict()
                item.pop('lostDate', None)
                
                inventory_df = pd.concat([inventory_df, pd.DataFrame([item])], ignore_index=True)
                lost_df = lost_df[lost_df['id'] != item_id]
            
            save_csv(inventory_df, INVENTORY_CSV)
            save_csv(lost_df, LOST_CSV)
            st.rerun()
    else:
        st.info("暂无遗失")

# =========================
# 订阅管理页面
# =========================
elif page == "订阅管理":
    st.header("🔄 订阅服务管理")
    
    # 添加订阅
    with st.expander("➕ 添加新订阅", expanded=not subscriptions_db):
        st.markdown("""
        **订阅格式说明：**
        - 按月订阅：`订阅:M:25 Crunchyroll >> 9.99` (每月25日续费)
        - 按年订阅：`订阅:Y:0502 Adobe CC >> 599` (每年5月2日续费)
        """)
        
        sub_text = st.text_area(
            "输入订阅信息",
            value=f"""---
日期：{datetime.now().strftime('%Y-%m-%d')}
入金：PayPal
出金：信用卡
币种：EUR
类型：订阅服务
---

订阅:M:25 Crunchyroll >> 9.99
订阅:Y:0101 Adobe CC >> 599
""",
            height=200
        )
        
        if st.button("添加订阅"):
            new_subs = parse_subscription_input(sub_text)
            
            if new_subs:
                for sub in new_subs:
                    subscriptions_db[sub['name']] = sub
                    
                    # 标记为非买断商品
                    if sub['name'] not in products_db:
                        products_db[sub['name']] = {
                            'name': sub['name'],
                            'standardPrice': sub['price'],
                            'currency': sub['currency'],
                            'category': sub['category'],
                            'purchaseCount': 0,
                            'buyout': False  # 订阅服务
                        }
                    else:
                        products_db[sub['name']]['buyout'] = False
                    
                    # 立即创建首次订阅
                    item = {
                        'id': generate_product_id(sub['name']),
                        'name': sub['name'],
                        'category': sub['category'],
                        'actualPrice': sub['price'],
                        'standardPrice': sub['price'],
                        'currency': sub['currency'],
                        'purchaseDate': datetime.now().strftime('%Y-%m-%d'),
                        'source': sub['source'],
                        'account': sub['account'],
                        'invoiceName': f"订阅_{sub['name']}",
                        'discount': 0,
                        'inTransit': False,
                        'purchaseRate': get_exchange_rate(sub['currency'], datetime.now().strftime('%Y-%m-%d'))
                    }
                    
                    inventory_df = pd.concat([inventory_df, pd.DataFrame([item])], ignore_index=True)
                
                save_json(subscriptions_db, SUBSCRIPTIONS_JSON)
                save_json(products_db, PRODUCTS_JSON)
                save_csv(inventory_df, INVENTORY_CSV)
                
                st.success(f"✅ 成功添加 {len(new_subs)} 个订阅服务！")
                st.rerun()
    
    # 当前订阅列表
    st.subheader("📋 当前订阅")
    
    if subscriptions_db:
        for sub_name, sub_info in subscriptions_db.items():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])
            
            with col1:
                period_text = "月付" if sub_info['period'] == 'M' else "年付"
                st.write(f"**{sub_name}** ({period_text})")
            
            with col2:
                st.write(f"{sub_info['price']} {sub_info['currency']}")
            
            with col3:
                next_date = datetime.strptime(sub_info['nextDate'], '%Y-%m-%d').date()
                days_left = (next_date - datetime.now().date()).days
                st.write(f"下次: {sub_info['nextDate']} ({days_left}天)")
            
            with col4:
                if st.button("🗑️", key=f"del_{sub_name}"):
                    del subscriptions_db[sub_name]
                    save_json(subscriptions_db, SUBSCRIPTIONS_JSON)
                    st.rerun()
    else:
        st.info("暂无订阅服务")
    
    # 订阅统计
    if subscriptions_db:
        st.subheader("📊 订阅统计")
        
        monthly_total = sum([s['price'] for s in subscriptions_db.values() if s['period'] == 'M'])
        yearly_total = sum([s['price'] for s in subscriptions_db.values() if s['period'] == 'Y'])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("订阅总数", len(subscriptions_db))
        with col2:
            st.metric("月付总额", f"{monthly_total:.2f} EUR")
        with col3:
            st.metric("年付总额", f"{yearly_total:.2f} EUR")

# =========================
# 遗失页面
# =========================
elif page == "遗失":
    st.header("❌ 遗失物品")
    
    if not lost_df.empty:
        st.dataframe(lost_df[['name', 'lostDate', 'actualPrice']], hide_index=True)
        
        selected_lost = st.multiselect(
            "找回",
            lost_df['id'].tolist(),
            format_func=lambda x: lost_df[lost_df['id'] == x]['name'].values[0]
        )
        
        if selected_lost and st.button("🔄 确认找回"):
            for item_id in selected_lost:
                item = lost_df[lost_df['id'] == item_id].iloc[0].to_dict()
                item.pop('lostDate', None)
                
                inventory_df = pd.concat([inventory_df, pd.DataFrame([item])], ignore_index=True)
                lost_df = lost_df[lost_df['id'] != item_id]
            
            save_csv(inventory_df, INVENTORY_CSV)
            save_csv(lost_df, LOST_CSV)
            st.rerun()
    else:
        st.info("暂无遗失")

# =========================
# 报表页面
# =========================
elif page == "报表":
    st.header("📊 统计报表")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("库存", len(inventory_df))
    with col2:
        st.metric("已出库", len(history_df))
    with col3:
        st.metric("遗失", len(lost_df))
    
    st.subheader("📈 支出趋势")
    
    trend_view = st.radio("", ["周", "月"], horizontal=True)
    currency = st.selectbox("币种", ['EUR', 'CNY', 'USD', 'JPY'])
    
    all_items = pd.concat([inventory_df, history_df], ignore_index=True)
    now = datetime.now()
    
    if trend_view == "周":
        days_range = 7
        labels = ['日', '一', '二', '三', '四', '五', '六']
    else:
        days_range = 30
        labels = [f"{i+1}" for i in range(30)]
    
    current_data = [0] * len(labels)
    previous_data = [0] * len(labels)
    
    for _, item in all_items.iterrows():
        try:
            date = datetime.strptime(str(item['purchaseDate']), '%Y-%m-%d')
            days_diff = (now - date).days
            
            eur_value = to_eur(item['actualPrice'], item['currency'], item['purchaseDate'])
            
            if currency != 'EUR':
                rate = get_exchange_rate(currency, item['purchaseDate'])
                value = eur_value * rate
            else:
                value = eur_value
            
            if 0 <= days_diff < days_range:
                idx = days_range - 1 - days_diff
                if 0 <= idx < len(current_data):
                    current_data[idx] += value
            elif days_range <= days_diff < days_range * 2:
                idx = days_range * 2 - 1 - days_diff
                if 0 <= idx < len(previous_data):
                    previous_data[idx] += value
        except:
            pass
    
    for i in range(1, len(current_data)):
        current_data[i] += current_data[i-1]
        previous_data[i] += previous_data[i-1]
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=labels,
        y=previous_data,
        name=f'上{trend_view}',
        marker_color='rgba(251, 146, 60, 0.5)'
    ))
    
    fig.add_trace(go.Scatter(
        x=labels,
        y=current_data,
        name=f'本{trend_view}',
        line=dict(color='rgb(234, 88, 12)', width=3),
        mode='lines+markers'
    ))
    
    fig.update_layout(
        height=400,
        yaxis_title=f'累计 ({currency})',
        hovermode='x unified'
    )
    
    st.plotly_chart(fig, use_container_width=True)
    
    # 账户流水分析
    st.subheader("💳 账户流水分析")
    
    st.info("⚠️ 此图展示各账户的交易金额分布，合计可能不等于实际消费总额（因转账、退款等操作）")
    
    # 时间筛选
    flow_period = st.selectbox("时间范围", ["本月", "本季", "本年", "全部"], key="flow_period")
    
    # 筛选数据
    flow_items = pd.concat([inventory_df, history_df], ignore_index=True)
    
    if flow_period == "本月":
        start_date = datetime.now().replace(day=1)
        flow_items = flow_items[pd.to_datetime(flow_items['purchaseDate']) >= start_date]
    elif flow_period == "本季":
        current_month = datetime.now().month
        quarter_start_month = ((current_month - 1) // 3) * 3 + 1
        start_date = datetime.now().replace(month=quarter_start_month, day=1)
        flow_items = flow_items[pd.to_datetime(flow_items['purchaseDate']) >= start_date]
    elif flow_period == "本年":
        start_date = datetime.now().replace(month=1, day=1)
        flow_items = flow_items[pd.to_datetime(flow_items['purchaseDate']) >= start_date]
    
    # 计算流水（转换为EUR）
    flow_items['eur_amount'] = flow_items.apply(
        lambda row: to_eur(row['actualPrice'], row['currency'], row['purchaseDate']),
        axis=1
    )
    
    # 入金账户流水（商家）
    source_flow = flow_items[flow_items['source'].notna()].groupby('source')['eur_amount'].sum().sort_values(ascending=False)
    
    # 出金账户流水（支付方式）
    account_flow = flow_items[flow_items['account'].notna()].groupby('account')['eur_amount'].sum().sort_values(ascending=False)
    
    # 双列展示
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**入金账户流水（商家）**")
        if not source_flow.empty:
            fig_source = go.Figure(data=[
                go.Bar(
                    x=source_flow.index,
                    y=source_flow.values,
                    marker_color='rgba(251, 146, 60, 0.8)',
                    text=[f"{v:.2f}" for v in source_flow.values],
                    textposition='auto'
                )
            ])
            fig_source.update_layout(
                height=300,
                xaxis_title="商家",
                yaxis_title="金额 (EUR)",
                showlegend=False
            )
            st.plotly_chart(fig_source, use_container_width=True)
            st.caption(f"合计: {source_flow.sum():.2f} EUR")
        else:
            st.info("暂无数据")
    
    with col2:
        st.write("**出金账户流水（支付方式）**")
        if not account_flow.empty:
            fig_account = go.Figure(data=[
                go.Bar(
                    x=account_flow.index,
                    y=account_flow.values,
                    marker_color='rgba(234, 88, 12, 0.8)',
                    text=[f"{v:.2f}" for v in account_flow.values],
                    textposition='auto'
                )
            ])
            fig_account.update_layout(
                height=300,
                xaxis_title="支付方式",
                yaxis_title="金额 (EUR)",
                showlegend=False
            )
            st.plotly_chart(fig_account, use_container_width=True)
            st.caption(f"合计: {account_flow.sum():.2f} EUR")
        else:
            st.info("暂无数据")
# =========================
# 指南页面
# =========================
elif page == "操作指南":
    st.header("✋🏻操作指南")
    st.markdown("_更新日期：二零二五年九月二十二日_")
    st.markdown("""
        - 汇率信息需要手动添加，建议每月1日或者汇率大幅变动时添加。目前支持欧元EUR、人民币CNY、美元USD和日元JPY。
        - AA制商品：提前区分aa制中自己实际使用的部分和其他人的部分，将自用部分惯常分类，其他人的部分记录为AA款等类别，出库时首款直接删除。对于收款时接收的零头小钱，不再计算。
        - 本软件的售出功能，不会改变开支趋势计算，类期货投资不是La Mer的宗旨，La Mer追求立足当下的节省模式。
    """)

st.sidebar.markdown("---")
st.sidebar.caption("La Mer v1.31.250922")
st.sidebar.caption("CREDIT")
st.sidebar.caption("Designer: 巫獭")
st.sidebar.caption("Senior Engineer: Claude Pro Sonnet 4")
st.sidebar.caption("Technical Support: Streamlit (PyPack)")