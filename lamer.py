import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import re
from datetime import datetime, timedelta
import plotly.graph_objects as go
from pathlib import Path
import time 
import os 

# ==================== 页面配置 ====================
st.set_page_config(
    page_title="La Mer 1.50",
    page_icon="🌊",
    layout="wide"
)

st.sidebar.title("La Mer v1.50")

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
GOALS_JSON = DATA_DIR / "goals.json" 

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
        return round(float(amount), 2)  # 🔥 即使是EUR也保留两位小数
    rate = get_exchange_rate(currency, purchase_date)
    return round(amount / rate, 2)  # 🔥 转换后保留两位小数

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
            
            eur_value = to_eur(actual_price, currency, purchase_date)


            item = {
                'id': generate_product_id(product_name),
                'name': product_name,
                'category': current_category,
                'actualPrice': round(float(actual_price), 2),  # 🔥 原价格也保留两位
                'standardPrice': round(float(standard_price), 2),  # 🔥 标准价也保留两位
                'currency': currency,
                'purchaseDate': purchase_date,
                'source': metadata.get('入金', ''),
                'account': metadata.get('出金', ''),
                'invoiceName': invoice_name,
                'discount': discount,
                'inTransit': False,
                'purchaseRate': purchase_rate,
                'eurValue': eur_value
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
goals_db = load_json(GOALS_JSON, {
    'target_engel': 35,           # 改为 28
    'target_meal_freq': 35,       # 保持
    'target_daily_food': 12,      # 改为 7
    'food_categories': [...]
})

exchange_rates_df = init_exchange_rates()

# 检查订阅续费
inventory_df, history_df, subscriptions_db, renewed_subs = check_subscriptions(
    subscriptions_db, inventory_df, history_df, deposits_db
)

if renewed_subs:
    save_csv(inventory_df, INVENTORY_CSV)
    save_csv(history_df, HISTORY_CSV)
    save_json(subscriptions_db, SUBSCRIPTIONS_JSON)


# ==================== 桑基图分析 - 函数定义部分 ====================
# 这部分代码应该放在主程序的函数定义区域（其他页面函数定义之后）

def load_platform_colors(platform_colors_json):
    """加载平台颜色配置（强制重新加载版本 + 格式验证）"""
    import json
    import re
    
    if platform_colors_json.exists():
        try:
            with open(platform_colors_json, 'r', encoding='utf-8') as f:
                colors = json.load(f)
            
            # 过滤并修复颜色配置
            fixed_colors = {}
            errors = []
            
            for k, v in colors.items():
                # 跳过注释键
                if k.startswith('_'):
                    continue
                
                original_v = v
                
                # 修复常见错误
                # 1. rbga → rgba
                v = v.replace('rbga', 'rgba').replace('RBGA', 'RGBA')
                
                # 2. 缺少右括号
                if v.count('(') > v.count(')'):
                    v = v + ')'
                
                # 3. 验证格式
                color_patterns = [
                    r'^rgba\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*[\d.]+\s*\)$',
                    r'^rgb\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)$',
                    r'^hsla\(\s*\d+\s*,\s*\d+%\s*,\s*\d+%\s*,\s*[\d.]+\s*\)$',
                    r'^hsl\(\s*\d+\s*,\s*\d+%\s*,\s*\d+%\s*\)$',
                    r'^#[0-9a-fA-F]{6}$',
                ]
                
                valid = any(re.match(pattern, v) for pattern in color_patterns)
                
                if not valid:
                    errors.append(f"❌ [{k}]: '{original_v}' → 格式错误，已跳过")
                    continue
                
                if original_v != v:
                    errors.append(f"⚠️ [{k}]: '{original_v}' → 已自动修复为 '{v}'")
                
                fixed_colors[k] = v
            
            return fixed_colors if fixed_colors else {"default": "rgba(150, 150, 150, 0.8)"}, errors
            
        except Exception as e:
            return {"default": "rgba(150, 150, 150, 0.8)"}, [f"❌ 读取配置文件失败: {e}"]
    else:
        return {"default": "rgba(150, 150, 150, 0.8)"}, ["⚠️ 未找到 platform_colors.json 配置文件"]


def get_platform_color(platform, platform_colors, debug=False):
    """获取平台颜色（带调试信息）"""
    platform_lower = platform.lower().strip()
    
    # 精确匹配
    if platform_lower in platform_colors:
        return platform_colors[platform_lower], "精确匹配", platform_lower
    
    # 模糊匹配
    for key in platform_colors:
        if key in platform_lower or platform_lower in key:
            return platform_colors[key], "模糊匹配", key
    
    # 自动生成
    hue = (hash(platform) % 360)
    return f'hsla({hue}, 65%, 50%, 0.8)', "自动配色", None


def create_sankey_diagram(df, platform_colors, height=1000, font_size=11):
    """创建金额归一化的三层桑基图（纯黑字体版）"""
    import plotly.graph_objects as go
    
    if df.empty:
        return None
    
    total_amount = df['eurValue'].sum()
    
    # 第一层：账户 → 来源
    layer1 = df.groupby(['account', 'source']).agg({
        'eurValue': ['sum', 'count']
    }).reset_index()
    layer1.columns = ['source', 'target', 'amount', 'count']
    layer1['normalized'] = layer1['amount'] / total_amount
    
    # 第二层：来源 → 类型
    layer2 = df.groupby(['source', 'category']).agg({
        'eurValue': ['sum', 'count']
    }).reset_index()
    layer2.columns = ['source', 'target', 'amount', 'count']
    layer2['normalized'] = layer2['amount'] / total_amount
    
    # 创建节点
    accounts = df['account'].unique().tolist()
    sources = df['source'].unique().tolist()
    categories = df['category'].unique().tolist()
    
    all_labels = accounts + sources + categories
    label_to_idx = {label: idx for idx, label in enumerate(all_labels)}
    
    # 节点配色
    node_colors = []
    for label in all_labels:
        if label in accounts:
            # 左侧账户：暗金色
            node_colors.append('rgba(184, 134, 11, 0.85)')
        elif label in sources:
            color, _, _ = get_platform_color(label, platform_colors)
            node_colors.append(color)
        else:
            # 右侧类别：翡翠绿
            node_colors.append('rgba(80, 200, 120, 0.85)')
    
    # 处理第一层
    layer1_source_idx = [label_to_idx[s] for s in layer1['source']]
    layer1_target_idx = [label_to_idx[t] for t in layer1['target']]
    layer1_values = layer1['normalized'].tolist()
    layer1_amounts = layer1['amount'].tolist()
    layer1_counts = layer1['count'].tolist()
    layer1_targets = layer1['target'].tolist()
    
    # 第一层连接线颜色（固定透明度）
    layer1_colors = []
    for target in layer1_targets:
        platform_color, _, _ = get_platform_color(target, platform_colors)
        if 'rgba' in platform_color:
            parts = platform_color.split('(')[1].split(')')[0].split(',')
            layer1_colors.append(f'rgba({parts[0]}, {parts[1]}, {parts[2]}, 0.5)')
        elif 'hsla' in platform_color:
            parts = platform_color.split('(')[1].split(')')[0].split(',')
            layer1_colors.append(f'hsla({parts[0]}, {parts[1]}, {parts[2]}, 0.5)')
        else:
            layer1_colors.append('rgba(150, 150, 150, 0.5)')
    
    # 处理第二层
    layer2_source_idx = [label_to_idx[s] for s in layer2['source']]
    layer2_target_idx = [label_to_idx[t] for t in layer2['target']]
    layer2_values = layer2['normalized'].tolist()
    layer2_amounts = layer2['amount'].tolist()
    layer2_counts = layer2['count'].tolist()
    layer2_sources = layer2['source'].tolist()
    
    # 第二层连接线颜色
    layer2_colors = []
    for src in layer2_sources:
        platform_color, _, _ = get_platform_color(src, platform_colors)
        if 'rgba' in platform_color:
            parts = platform_color.split('(')[1].split(')')[0].split(',')
            layer2_colors.append(f'rgba({parts[0]}, {parts[1]}, {parts[2]}, 0.5)')
        elif 'hsla' in platform_color:
            parts = platform_color.split('(')[1].split(')')[0].split(',')
            layer2_colors.append(f'hsla({parts[0]}, {parts[1]}, {parts[2]}, 0.5)')
        else:
            layer2_colors.append('rgba(150, 150, 150, 0.5)')
    
    # 合并
    source_indices = layer1_source_idx + layer2_source_idx
    target_indices = layer1_target_idx + layer2_target_idx
    values = layer1_values + layer2_values
    actual_amounts = layer1_amounts + layer2_amounts
    actual_counts = layer1_counts + layer2_counts
    link_colors = layer1_colors + layer2_colors
    
    # 自定义数据
    customdata = [[amount, count, amount/total_amount*100] 
                  for amount, count in zip(actual_amounts, actual_counts)]
    
    # 创建图表 - 不设置任何字体样式
    fig = go.Figure(data=[go.Sankey(
        arrangement='snap',
        node=dict(
            pad=25,
            thickness=30,
            line=dict(color="black", width=0.5),
            label=all_labels,
            color=node_colors,
            hovertemplate='%{label}<br>占比: %{value:.1%}<extra></extra>',
        ),
        link=dict(
            source=source_indices,
            target=target_indices,
            value=values,
            color=link_colors,
            customdata=customdata,
            hovertemplate=(
                '%{source.label} → %{target.label}<br>'
                '金额: €%{customdata[0]:.2f}<br>'
                '次数: %{customdata[1]}<br>'
                '占比: %{customdata[2]:.1f}%<extra></extra>'
            )
        )
    )])
    
    # 布局设置 - 去除所有字体样式配置
    fig.update_layout(
        height=height,
        margin=dict(l=250, r=250, t=50, b=50),
        plot_bgcolor='white',
        paper_bgcolor='white'
    )
    
    # 只设置纯黑色文字，无任何其他样式
    fig.update_traces(
        textfont=dict(
            color='#000000',
            size=font_size
        )
    )
    
    return fig


def render_sankey_with_highlight(fig, height=1000):
    """使用自定义JS渲染桑基图，支持hover highlight（悬停高亮 + 淡化其余）"""
    
    fig_json = fig.to_json()
    
    html_content = f"""
    <html>
    <head>
        <script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
        <style>
            body {{ margin: 0; padding: 0; background: white; }}
            #sankey-chart {{ width: 100%; height: {height}px; }}
        </style>
    </head>
    <body>
        <div id="sankey-chart"></div>
        <script>
            var figData = {fig_json};
            
            Plotly.newPlot('sankey-chart', figData.data, figData.layout, {{
                responsive: true,
                displaylogo: false,
                modeBarButtonsToRemove: ['select2d', 'lasso2d']
            }}).then(function(gd) {{
                
                // 保存原始颜色
                var trace = gd.data[0];
                var originalLinkColors = trace.link.color.slice();
                var originalNodeColors = trace.node.color.slice();
                var sources = trace.link.source;
                var targets = trace.link.target;
                var numNodes = trace.node.label.length;
                
                // 辅助：将颜色设置为淡化版本
                function fadeColor(color, alpha) {{
                    if (!color) return 'rgba(200,200,200,' + alpha + ')';
                    
                    // rgba(...)
                    var rgbaMatch = color.match(/rgba?\\(([^)]+)\\)/);
                    if (rgbaMatch) {{
                        var parts = rgbaMatch[1].split(',').map(s => s.trim());
                        return 'rgba(' + parts[0] + ',' + parts[1] + ',' + parts[2] + ',' + alpha + ')';
                    }}
                    
                    // hsla(...)
                    var hslaMatch = color.match(/hsla?\\(([^)]+)\\)/);
                    if (hslaMatch) {{
                        var parts = hslaMatch[1].split(',').map(s => s.trim());
                        return 'hsla(' + parts[0] + ',' + parts[1] + ',' + parts[2] + ',' + alpha + ')';
                    }}
                    
                    // hex → rgba
                    if (color.startsWith('#') && color.length === 7) {{
                        var r = parseInt(color.slice(1,3), 16);
                        var g = parseInt(color.slice(3,5), 16);
                        var b = parseInt(color.slice(5,7), 16);
                        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
                    }}
                    
                    return 'rgba(200,200,200,' + alpha + ')';
                }}
                
                // 辅助：将颜色设置为高亮版本（提高不透明度）
                function highlightColor(color, alpha) {{
                    if (!color) return 'rgba(200,200,200,' + alpha + ')';
                    
                    var rgbaMatch = color.match(/rgba?\\(([^)]+)\\)/);
                    if (rgbaMatch) {{
                        var parts = rgbaMatch[1].split(',').map(s => s.trim());
                        return 'rgba(' + parts[0] + ',' + parts[1] + ',' + parts[2] + ',' + alpha + ')';
                    }}
                    
                    var hslaMatch = color.match(/hsla?\\(([^)]+)\\)/);
                    if (hslaMatch) {{
                        var parts = hslaMatch[1].split(',').map(s => s.trim());
                        return 'hsla(' + parts[0] + ',' + parts[1] + ',' + parts[2] + ',' + alpha + ')';
                    }}
                    
                    if (color.startsWith('#') && color.length === 7) {{
                        var r = parseInt(color.slice(1,3), 16);
                        var g = parseInt(color.slice(3,5), 16);
                        var b = parseInt(color.slice(5,7), 16);
                        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
                    }}
                    
                    return 'rgba(200,200,200,' + alpha + ')';
                }}
                
                // 找到与某个节点相关的所有链接和节点
                function getConnected(nodeIdx) {{
                    var connLinks = new Set();
                    var connNodes = new Set();
                    connNodes.add(nodeIdx);
                    
                    for (var i = 0; i < sources.length; i++) {{
                        if (sources[i] === nodeIdx || targets[i] === nodeIdx) {{
                            connLinks.add(i);
                            connNodes.add(sources[i]);
                            connNodes.add(targets[i]);
                        }}
                    }}
                    return {{ links: connLinks, nodes: connNodes }};
                }}
                
                // 节点悬停事件
                gd.on('plotly_hover', function(eventData) {{
                    if (!eventData || !eventData.points || !eventData.points[0]) return;
                    var point = eventData.points[0];
                    
                    // 判断是否悬停在节点上（Sankey 的节点 hover）
                    if (point.pointNumber !== undefined && point.group !== undefined) {{
                        var nodeIdx = point.pointNumber;
                        var conn = getConnected(nodeIdx);
                        
                        // 淡化所有链接
                        var newLinkColors = [];
                        for (var i = 0; i < originalLinkColors.length; i++) {{
                            if (conn.links.has(i)) {{
                                newLinkColors.push(highlightColor(originalLinkColors[i], 0.85));
                            }} else {{
                                newLinkColors.push(fadeColor(originalLinkColors[i], 0.08));
                            }}
                        }}
                        
                        // 淡化所有节点
                        var newNodeColors = [];
                        for (var j = 0; j < originalNodeColors.length; j++) {{
                            if (conn.nodes.has(j)) {{
                                newNodeColors.push(highlightColor(originalNodeColors[j], 1.0));
                            }} else {{
                                newNodeColors.push(fadeColor(originalNodeColors[j], 0.15));
                            }}
                        }}
                        
                        Plotly.restyle(gd, {{
                            'link.color': [newLinkColors],
                            'node.color': [newNodeColors]
                        }});
                    }}
                }});
                
                // 鼠标离开 → 恢复原始颜色
                gd.on('plotly_unhover', function() {{
                    Plotly.restyle(gd, {{
                        'link.color': [originalLinkColors.slice()],
                        'node.color': [originalNodeColors.slice()]
                    }});
                }});
            }});
        </script>
    </body>
    </html>
    """
    
    components.html(html_content, height=height + 20, scrolling=False)


def force_load_csv_sankey(filepath, columns):
    """强制读取CSV，不使用任何缓存（桑基图专用）"""
    import pandas as pd
    import os
    
    if not os.path.exists(filepath):
        return pd.DataFrame(columns=columns)
    
    # 直接读取，每次都是新的
    df = pd.read_csv(filepath)
    
    # 确保所有必需列都存在
    for col in columns:
        if col not in df.columns:
            df[col] = None
    
    return df







# ==================== UI界面 ====================
# ==                                          ===

# ==                                          ===
# ==                                          ===
# ==================== UI界面 ====================

st.sidebar.caption("聯邦電氣化黨 | LaMer AG ")
page = st.sidebar.radio("导航", ["入库", "检视", "遗失", "订阅", "趋势", "效用", "采购", "特异", "桑基", "目标", "说明"])
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
            
            if currencies:
                success_msg += f"，总计 {currency_summary}"
            if deposit_returns:
                success_msg += f"\n♻️ 返还 {sum([r['count'] for r in deposit_returns])} 个Pfand"
            
            st.success(success_msg)
            time.sleep(1)  # 需要import time
            st.rerun()
        else:
            st.error("❌ 没有解析到商品")

# ==================== 检视页面 ====================
elif page == "检视":

    st.header("📊 货物记录")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("库存", len(inventory_df))
    with col2:
        st.metric("已出库", len(history_df))
    with col3:
        st.metric("遗失", len(lost_df))


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
        
        # 订阅服务标识 - 修复：显示购买月份而非扣款日
        def format_name(row):
            name = row['name']
            if name in subscriptions_db:
                sub_info = subscriptions_db[name]
                period_mark = 'M' if sub_info['period'] == 'M' else 'Y'
                # 从purchaseDate提取月份（M）或月日（Y）
                purchase_date = row['purchaseDate']
                if period_mark == 'M':
                    # 月付：显示购买月份，如 M01
                    date_str = purchase_date[5:7]  # 提取月份 YYYY-MM-DD -> MM
                else:
                    # 年付：显示购买月日，如 Y0114
                    date_str = purchase_date[5:7] + purchase_date[8:10]  # MM + DD
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
            format_func=lambda x: (
                f"{filtered_df[filtered_df['id'] == x]['name'].values[0]} "
                f"[{filtered_df[filtered_df['id'] == x]['purchaseDate'].values[0]}]"
            )
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
                st.write("**垫付结清**")
                sell_price = st.number_input("售价", 0.0, step=0.1)
                if accounts_db:
                    sell_account = st.selectbox("账户", accounts_db)
                else:
                    sell_account = st.text_input("账户")
                
                if st.button("确认清账"):
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
                    st.success("💰 清账成功，指定内容将不再计入支出趋势图")
                    st.rerun()
            
            with col4:
                st.write("**删除 /退回押金**")
                st.caption("删除误操作或退回押金，相关记录不会计入支出趋势图。")
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
elif page == "订阅":
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
入金：
出金：
币种：EUR
类型：
---

订阅:M:25 Crunchyroll >> 6.99
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
                time.sleep(2)  # 需要import time
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
        #with col2:
            #st.metric("月付总额", f"{monthly_total:.2f} EUR")
        #with col3:
            #st.metric("年付总额", f"{yearly_total:.2f} EUR")


# =========================
# 开支趋势页面
# =========================
elif page == "趋势":

    

    # 支出趋势部分

    st.subheader("📈 支出趋势")

    # 视图模式选择
    view_mode = st.radio("", ["周对比", "月对比"], horizontal=True)

    # 获取所有数据
    all_items = pd.concat([inventory_df, history_df, lost_df], ignore_index=True)

    if view_mode == "周对比":
        # ========== 周对比视图 ==========
        currency = st.selectbox("币种", ['EUR', 'CNY', 'USD', 'JPY'], key="week_currency")
        
        today = datetime.now().date()
        
        # 本周日期（从周一开始）
        week_start = today - timedelta(days=today.weekday())
        current_dates = [week_start + timedelta(days=i) for i in range(7)]
        
        # 上周日期
        prev_week_start = week_start - timedelta(days=7)
        previous_dates = [prev_week_start + timedelta(days=i) for i in range(7)]
        
        # 标签显示星期格式
        labels = ['一', '二', '三', '四', '五', '六', '日']
        
        # 准备数据数组
        current_data = [0] * len(current_dates)
        previous_data = [0] * len(previous_dates)
        
        # 按真实日期分组数据
        for _, item in all_items.iterrows():
            try:
                item_date = datetime.strptime(str(item['purchaseDate']), '%Y-%m-%d').date()
                
                # 计算EUR价值
                eur_value = to_eur(item['actualPrice'], item['currency'], item['purchaseDate'])
                if currency != 'EUR':
                    rate = get_exchange_rate(currency, item['purchaseDate'])
                    value = eur_value * rate
                else:
                    value = eur_value
                
                # 分配到对应日期
                if item_date in current_dates:
                    idx = current_dates.index(item_date)
                    current_data[idx] += value
                elif item_date in previous_dates:
                    idx = previous_dates.index(item_date)
                    previous_data[idx] += value
                    
            except (ValueError, KeyError, TypeError):
                continue
        
        # 计算累计值
        for i in range(1, len(current_data)):
            current_data[i] += current_data[i-1]
        for i in range(1, len(previous_data)):
            previous_data[i] += previous_data[i-1]
        
        # 截取到今天
        today_idx = -1
        try:
            today_idx = current_dates.index(today)
        except ValueError:
            today_idx = len(current_dates) - 1
        
        current_data_until_today = current_data[:today_idx + 1]
        labels_until_today = labels[:today_idx + 1]
        
        fig = go.Figure()
        
        # 本周数据（只到今天）
        fig.add_trace(go.Scatter(
            x=list(range(len(labels_until_today))),
            y=current_data_until_today,
            line=dict(color='rgb(234, 88, 12)', width=3),
            mode='lines',
            name='本周'
        ))
        
        # 上周数据（完整显示）
        fig.add_trace(go.Scatter(
            x=list(range(len(labels))),
            y=previous_data,
            name='上周',
            line=dict(color='rgba(251, 146, 60, 0.5)', width=2),
            mode='lines'
        ))
        
        fig.update_layout(
            height=400,
            yaxis_title=f'累计支出 ({currency})',
            hovermode='x unified',
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            xaxis=dict(
                tickmode='array',
                tickvals=list(range(len(labels))),
                ticktext=labels,
                range=[-0.5, len(labels)-0.5]
            ),
            margin=dict(l=50, r=50, t=50, b=50)
        )
        
        st.plotly_chart(fig, use_container_width=True)

    else:
        # ========== 月对比视图 ==========
        if not all_items.empty:
            # 提取所有月份
            all_items['month'] = pd.to_datetime(all_items['purchaseDate']).dt.to_period('M')
            available_months = sorted(all_items['month'].unique(), reverse=True)
            available_months_str = [str(m) for m in available_months]
            
            # 月份选择器
            col1, col2, col3 = st.columns([2, 2, 2])
            
            with col1:
                # 默认选择本月
                current_month = pd.Period(datetime.now(), freq='M')
                default_month1 = str(current_month) if current_month in available_months else available_months_str[0]
                month1 = st.selectbox("对比月份 1", available_months_str, 
                                    index=available_months_str.index(default_month1))
            
            with col2:
                # 默认选择上月
                prev_month = current_month - 1
                default_month2 = str(prev_month) if prev_month in available_months else (
                    available_months_str[1] if len(available_months_str) > 1 else available_months_str[0]
                )
                month2 = st.selectbox("对比月份 2", available_months_str,
                                    index=available_months_str.index(default_month2))
            
            with col3:
                currency = st.selectbox("币种", ['EUR', 'CNY', 'USD', 'JPY'], key="month_currency")
            
            # 转换选择的月份
            month1_period = pd.Period(month1)
            month2_period = pd.Period(month2)
            
            # 生成两个月份的日期列表
            month1_start = month1_period.to_timestamp()
            month1_end = (month1_period + 1).to_timestamp() - timedelta(days=1)
            
            month2_start = month2_period.to_timestamp()
            month2_end = (month2_period + 1).to_timestamp() - timedelta(days=1)
            
            # 生成日期范围
            month1_dates = []
            current_date = month1_start.date()
            while current_date <= month1_end.date():
                month1_dates.append(current_date)
                current_date += timedelta(days=1)
            
            month2_dates = []
            current_date = month2_start.date()
            while current_date <= month2_end.date():
                month2_dates.append(current_date)
                current_date += timedelta(days=1)
            
            # 标签（日期）
            labels1 = [str(d.day) for d in month1_dates]
            labels2 = [str(d.day) for d in month2_dates]
            
            # 准备数据数组
            month1_data = [0] * len(month1_dates)
            month2_data = [0] * len(month2_dates)
            
            # 按日期分组数据
            for _, item in all_items.iterrows():
                try:
                    item_date = datetime.strptime(str(item['purchaseDate']), '%Y-%m-%d').date()
                    
                    # 计算EUR价值
                    eur_value = to_eur(item['actualPrice'], item['currency'], item['purchaseDate'])
                    if currency != 'EUR':
                        rate = get_exchange_rate(currency, item['purchaseDate'])
                        value = eur_value * rate
                    else:
                        value = eur_value
                    
                    # 分配到对应日期
                    if item_date in month1_dates:
                        idx = month1_dates.index(item_date)
                        month1_data[idx] += value
                    elif item_date in month2_dates:
                        idx = month2_dates.index(item_date)
                        month2_data[idx] += value
                        
                except (ValueError, KeyError, TypeError):
                    continue
            
            # 计算累计值
            for i in range(1, len(month1_data)):
                month1_data[i] += month1_data[i-1]
            for i in range(1, len(month2_data)):
                month2_data[i] += month2_data[i-1]
            
            # 截取到今天（仅对当月有效）
            today = datetime.now().date()
            
            if today in month1_dates:
                today_idx1 = month1_dates.index(today)
                month1_data_display = month1_data[:today_idx1 + 1]
                labels1_display = labels1[:today_idx1 + 1]
            else:
                month1_data_display = month1_data
                labels1_display = labels1
            
            # 绘制对比图
            fig = go.Figure()
            
            # 月份1数据
            fig.add_trace(go.Scatter(
                x=list(range(len(labels1_display))),
                y=month1_data_display,
                line=dict(color='rgb(234, 88, 12)', width=3),
                mode='lines',
                name=f'{month1}'
            ))
            
            # 月份2数据（完整显示）
            fig.add_trace(go.Scatter(
                x=list(range(len(labels2))),
                y=month2_data,
                name=f'{month2}',
                line=dict(color='rgba(251, 146, 60, 0.5)', width=2),
                mode='lines'
            ))
            
            # 使用较长的那个月份的标签数量
            max_len = max(len(labels1), len(labels2))
            all_labels = labels1 if len(labels1) >= len(labels2) else labels2
            
            # 更新布局
            fig.update_layout(
                height=400,
                yaxis_title=f'累计支出 ({currency})',
                xaxis_title='日期',
                hovermode='x unified',
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                ),
                xaxis=dict(
                    tickmode='array',
                    tickvals=list(range(len(all_labels))),
                    ticktext=all_labels,
                    range=[-0.5, len(all_labels)-0.5]
                ),
                margin=dict(l=50, r=50, t=50, b=50)
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 显示统计对比
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(f"{month1} 总支出", f"{month1_data[-1]:.2f} {currency}")
            with col2:
                st.metric(f"{month2} 总支出", f"{month2_data[-1]:.2f} {currency}")
            with col3:
                diff = month1_data[-1] - month2_data[-1]
                st.metric("差额", f"{diff:.2f} {currency}", 
                        delta=f"{diff:.2f}" if diff != 0 else "0")
        
        else:
            st.info("暂无数据")


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



# ==================== 产品利用率检视页面 ====================
elif page == "效用":
    st.header("🫗 利用率检视")
    
    if not history_df.empty:
        # 筛选出有利用率数据的记录
        utilization_df = history_df[history_df['utilization'].notna()].copy()
        
        if not utilization_df.empty:
            # 按商品名称分组，计算平均利用率和统计信息
            utilization_stats = utilization_df.groupby('name').agg({
                'utilization': ['mean', 'count', 'min', 'max'],
                'actualPrice': 'mean',
                'currency': 'first',
                'category': 'first',
                'daysInService': 'mean'
            }).reset_index()
            
            # 扁平化列名
            utilization_stats.columns = [
                'name', 'avg_utilization', 'count', 'min_utilization', 'max_utilization',
                'avg_price', 'currency', 'category', 'avg_days'
            ]
            
            # 计算EUR价值（使用最近的汇率）
            utilization_stats['eur_value'] = utilization_stats.apply(
                lambda row: to_eur(row['avg_price'], row['currency'], datetime.now().strftime('%Y-%m-%d')),
                axis=1
            )
            
            # 筛选控件
            col1, col2, col3 = st.columns([2, 2, 2])
            
            with col1:
                # 利用率范围筛选
                min_util, max_util = st.slider(
                    "利用率范围 (%)", 
                    0, 100, (0, 100),
                    help="筛选平均利用率在此范围内的商品"
                )
            
            with col2:
                # 类别筛选
                categories = ['全部'] + sorted(utilization_stats['category'].unique().tolist())
                selected_category = st.selectbox("商品类别", categories)
            
            with col3:
                # 排序方式
                sort_options = {
                    '平均利用率（降序）': ('avg_utilization', False),
                    '平均利用率（升序）': ('avg_utilization', True),
                    '购买次数（降序）': ('count', False),
                    '平均价格（降序）': ('eur_value', False),
                    '平均使用天数（降序）': ('avg_days', False)
                }
                sort_choice = st.selectbox("排序方式", list(sort_options.keys()))
                sort_col, sort_asc = sort_options[sort_choice]
            
            # 应用筛选
            filtered_stats = utilization_stats[
                (utilization_stats['avg_utilization'] >= min_util) &
                (utilization_stats['avg_utilization'] <= max_util)
            ].copy()
            
            if selected_category != '全部':
                filtered_stats = filtered_stats[filtered_stats['category'] == selected_category]
            
            # 排序
            filtered_stats = filtered_stats.sort_values(sort_col, ascending=sort_asc)
            
            # 显示统计摘要
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("商品种类", len(filtered_stats))
            
            with col2:
                overall_avg = filtered_stats['avg_utilization'].mean()
                st.metric("整体平均利用率", f"{overall_avg:.1f}%")
            
            with col3:
                high_util_count = len(filtered_stats[filtered_stats['avg_utilization'] >= 80])
                st.metric("高利用率商品(≥80%)", high_util_count)
            
            with col4:
                low_util_count = len(filtered_stats[filtered_stats['avg_utilization'] < 50])
                st.metric("低利用率商品(<50%)", low_util_count)
            
            # 主表格
            st.subheader("📋 商品利用率详情")
            
            # 准备显示数据
            display_data = filtered_stats.copy()
            display_data['avg_utilization'] = display_data['avg_utilization'].round(1)
            display_data['avg_price'] = display_data['avg_price'].round(2)
            display_data['eur_value'] = display_data['eur_value'].round(2)
            display_data['avg_days'] = display_data['avg_days'].round(1)
            
            # 格式化显示列
            display_columns = {
                'name': '商品名称',
                'category': '类别',
                'avg_utilization': '平均利用率(%)',
                'count': '购买次数',
                'min_utilization': '最低利用率(%)',
                'max_utilization': '最高利用率(%)',
                'avg_price': '平均价格',
                'currency': '币种',
                'eur_value': '平均价格(EUR)',
                'avg_days': '平均使用天数'
            }
            
            # 添加利用率颜色标识
            def style_utilization(val):
                if pd.isna(val):
                    return ''
                if val >= 80:
                    return 'background-color: #dcfce7; color: #15803d'  # 绿色
                elif val >= 60:
                    return 'background-color: #fef3c7; color: #d97706'  # 黄色
                else:
                    return 'background-color: #fee2e2; color: #dc2626'  # 红色
            
            # 显示表格
            styled_df = display_data[list(display_columns.keys())].rename(columns=display_columns)
            
            # 应用样式
            styled_table = styled_df.style.applymap(
                style_utilization, 
                subset=['平均利用率(%)']
            ).format({
                '平均利用率(%)': '{:.1f}',
                '平均价格': '{:.2f}',
                '平均价格(EUR)': '{:.2f}',
                '平均使用天数': '{:.1f}'
            })
            
            st.dataframe(styled_table, use_container_width=True, hide_index=True)
                      
            # 详细商品信息（可展开）
            with st.expander("🔍 查看详细购买记录"):
                selected_product = st.selectbox(
                    "选择商品",
                    filtered_stats['name'].tolist(),
                    key="product_detail_select"
                )
                
                if selected_product:
                    product_records = utilization_df[utilization_df['name'] == selected_product].copy()
                    product_records = product_records.sort_values('checkoutDate', ascending=False)
                    
                    # 显示该商品的所有记录
                    detail_columns = [
                        'purchaseDate', 'checkoutDate', 'utilization', 'daysInService',
                        'actualPrice', 'currency', 'checkoutMode'
                    ]
                    
                    detail_display = {
                        'purchaseDate': '购买日期',
                        'checkoutDate': '出库日期',
                        'utilization': '利用率(%)',
                        'daysInService': '使用天数',
                        'actualPrice': '价格',
                        'currency': '币种',
                        'checkoutMode': '出库方式'
                    }
                    
                    st.dataframe(
                        product_records[detail_columns].rename(columns=detail_display),
                        use_container_width=True,
                        hide_index=True
                    )
                    
                    # 该商品的统计信息
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("总购买次数", len(product_records))
                    with col2:
                        st.metric("平均利用率", f"{product_records['utilization'].mean():.1f}%")
                    with col3:
                        st.metric("平均使用天数", f"{product_records['daysInService'].mean():.1f}")
            
        else:
            st.info("暂无已出库且有利用率记录的商品")
    else:
        st.info("暂无历史记录")

# =========================
# 采购页面
# =========================
elif page == "采购":
    st.header("🛒 购物清单")
    st.caption("基于最近出库商品生成（仅包含购买次数 > 1 的商品）")
    
    # 🔥 新增：类型筛选器
    with st.expander("⚙️ 设置清单类型", expanded=False):
        st.markdown("**选择购物清单包含的商品类型：**")
        available_categories = sorted(categories_db)
        
        # 从goals_db读取上次保存的清单类型配置（如果没有则使用所有类型）
        default_shopping_cats = goals_db.get('shopping_categories', available_categories)
        
        # 过滤掉不存在的默认值
        valid_defaults = [cat for cat in default_shopping_cats if cat in available_categories]
        
        selected_shopping_categories = st.multiselect(
            "选择哪些类型计入购物清单",
            available_categories,
            default=valid_defaults
        )
        
        if st.button("💾 保存清单类型设置"):
            goals_db['shopping_categories'] = selected_shopping_categories
            save_json(goals_db, GOALS_JSON)
            st.success("✅ 清单类型已保存！")
            time.sleep(1)
            st.rerun()
    
    # 获取当前的清单类型设置
    shopping_categories = goals_db.get('shopping_categories', categories_db)
    
    if not history_df.empty:
        # 获取出库记录，按日期降序排序
        recent_checkout = history_df.sort_values('checkoutDate', ascending=False)
        
        # 🔥 修改：先按类型筛选
        recent_checkout = recent_checkout[recent_checkout['category'].isin(shopping_categories)]
        
        # 筛选出购买次数 > 1 的商品
        eligible_products = set()
        for product_name, product_info in products_db.items():
            if product_info.get('purchaseCount', 0) > 1:
                eligible_products.add(product_name)
        
        # 从最近出库记录中筛选出最近的20件符合条件的商品
        shopping_list = []
        seen_names = set()
        
        for _, item in recent_checkout.iterrows():
            if len(shopping_list) >= 20:
                break
            
            if item['name'] in eligible_products and item['name'] not in seen_names:
                shopping_list.append(item)
                seen_names.add(item['name'])
        
        # ... 后续代码保持不变 ...
    
    if not history_df.empty:
        # 获取出库记录，按日期降序排序
        recent_checkout = history_df.sort_values('checkoutDate', ascending=False)
        
        # 筛选出购买次数 > 1 的商品
        eligible_products = set()
        for product_name, product_info in products_db.items():
            if product_info.get('purchaseCount', 0) > 1:
                eligible_products.add(product_name)
        
        # 从最近出库记录中筛选出最近的20件符合条件的商品
        shopping_list = []
        seen_names = set()
        
        for _, item in recent_checkout.iterrows():
            if len(shopping_list) >= 20:
                break
            
            if item['name'] in eligible_products and item['name'] not in seen_names:
                shopping_list.append(item)
                seen_names.add(item['name'])
        
        if shopping_list:
            # 创建展示数据
            display_items = []
            for idx, item in enumerate(shopping_list, 1):
                product_info = products_db.get(item['name'], {})
                display_items.append({
                    '序号': idx,
                    '商品名称': item['name'],
                    '类别': item['category'],
                    '最后购买价格': f"{item['actualPrice']:.2f}",
                    '币种': item['currency'],
                    '上次出库日期': item['checkoutDate'],
                    '购买次数': product_info.get('purchaseCount', 0)
                })
            
            display_df = pd.DataFrame(display_items)
            st.dataframe(display_df, hide_index=True, use_container_width=True)
            
            # 生成清单导出选项
            st.subheader("📋 清单生成")
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📋 复制清单文本"):
                    # 生成纯文本清单
                    text_list = ""
                    for idx, item in enumerate(shopping_list, 1):
                        text_list += f"{item['name']}_"
                        text_list += f"类别: {item['category']}_"
                        text_list += f"上次价格: {item['actualPrice']:.2f} {item['currency']}\n"
                    
                    st.code(text_list)
                    st.caption("可复制上方文本")
            
            with col2:
                if st.button("📊 显示统计"):
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        st.metric("清单商品数", len(shopping_list))
                    
                    with col_b:
                        total_price_eur = sum([
                            to_eur(item['actualPrice'], item['currency'], item['checkoutDate'])
                            for item in shopping_list
                        ])
                        st.metric("总预算(EUR)", f"{total_price_eur:.2f}")
                    
                    with col_c:
                        avg_purchase_count = sum([
                            products_db.get(item['name'], {}).get('purchaseCount', 0)
                            for item in shopping_list
                        ]) / len(shopping_list)
                        st.metric("平均购买次数", f"{avg_purchase_count:.1f}")
            
            # 按类别分组显示
            st.subheader("📂 按类别分组")
            
            categories_list = {}
            for item in shopping_list:
                cat = item['category'] if item['category'] else '未分类'
                if cat not in categories_list:
                    categories_list[cat] = []
                categories_list[cat].append(item['name'])
            
            for cat, items in sorted(categories_list.items()):
                with st.expander(f"**{cat}** ({len(items)}件)"):
                    for idx, name in enumerate(items, 1):
                        st.write(f"{idx}. {name}")
        
        else:
            st.info("暂无符合条件的商品（需要购买次数 > 1）")
    
    else:
        st.info("暂无出库记录")









# ==================== 特异商品页面 ====================
elif page == "特异":
    st.header("✨ 特异商品分析")
    st.caption("低频购买的商品，可能是精心挑选的自我奖励")
    
    # 阈值设置
    threshold = st.sidebar.slider("常规商品阈值（购买次数≥此值视为常规）", 1, 10, 2)
    
    # 合并所有消费数据（不含sold）
    all_expense = pd.concat([inventory_df, history_df, lost_df], ignore_index=True)
    
    if all_expense.empty:
        st.info("暂无消费记录")
    else:
        # 确保有eurValue列
        if 'eurValue' not in all_expense.columns:
            all_expense['eurValue'] = all_expense.apply(
                lambda row: to_eur(row['actualPrice'], row['currency'], row['purchaseDate']),
                axis=1
            )
        
        # 解析月份
        all_expense['purchaseDate'] = pd.to_datetime(all_expense['purchaseDate'], errors='coerce')
        all_expense = all_expense.dropna(subset=['purchaseDate'])
        all_expense['month'] = all_expense['purchaseDate'].dt.to_period('M')
        
        # 月份选择
        available_months = sorted(all_expense['month'].unique(), reverse=True)
        available_months_str = [str(m) for m in available_months]
        
        current_month = pd.Period(datetime.now(), freq='M')
        default_month = str(current_month) if current_month in available_months else available_months_str[0]
        
        selected_month = st.selectbox(
            "选择月份", 
            available_months_str,
            index=available_months_str.index(default_month) if default_month in available_months_str else 0
        )
        selected_period = pd.Period(selected_month)
        
        # 筛选当月数据
        month_data = all_expense[all_expense['month'] == selected_period].copy()
        
        if month_data.empty:
            st.info(f"{selected_month} 暂无消费记录")
        else:
            # 判断每个商品是常规还是特异
            # 基于 products_db 中的 purchaseCount
            def classify_item(name):
                # 订阅服务一律视为常规
                if name in subscriptions_db:
                    return 'regular'
                
                if name in products_db:
                    count = products_db[name].get('purchaseCount', 1)
                    return 'regular' if count >= threshold else 'occasional'
                return 'occasional'
            
            month_data['expense_type'] = month_data['name'].apply(classify_item)
            
            # 分离常规与特异
            regular_df = month_data[month_data['expense_type'] == 'regular']
            occasional_df = month_data[month_data['expense_type'] == 'occasional']
            
            regular_total = regular_df['eurValue'].sum()
            occasional_total = occasional_df['eurValue'].sum()
            total = regular_total + occasional_total
            
            # 概览指标
            st.subheader("📊 本月概览")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("总支出", f"€{total:.2f}")
            with col2:
                st.metric("常规支出", f"€{regular_total:.2f}")
            with col3:
                st.metric("特异支出", f"€{occasional_total:.2f}")
            with col4:
                ratio = (occasional_total / total * 100) if total > 0 else 0
                st.metric("特异占比", f"{ratio:.1f}%")
            
            st.markdown("---")
            
            # 特异商品清单
            st.subheader("✨ 特异商品清单")
            
            if occasional_df.empty:
                st.success("本月没有特异支出，全是常规消费！")
            else:
                # 按金额降序
                occasional_display = occasional_df[['name', 'category', 'purchaseDate', 'actualPrice', 'currency', 'eurValue']].copy()
                occasional_display = occasional_display.sort_values('eurValue', ascending=False)
                occasional_display['purchaseDate'] = occasional_display['purchaseDate'].dt.strftime('%Y-%m-%d')
                occasional_display['eurValue'] = occasional_display['eurValue'].round(2)
                
                # 添加购买次数信息
                occasional_display['历史购买次数'] = occasional_display['name'].apply(
                    lambda x: products_db.get(x, {}).get('purchaseCount', 1)
                )
                
                occasional_display.columns = ['商品名称', '类别', '购买日期', '价格', '币种', '价值(EUR)', '历史购买次数']
                
                st.dataframe(occasional_display, use_container_width=True, hide_index=True)
                
                # 按类别汇总
                with st.expander("📂 特异支出按类别汇总"):
                    cat_summary = occasional_df.groupby('category')['eurValue'].agg(['sum', 'count']).round(2)
                    cat_summary.columns = ['金额(EUR)', '件数']
                    cat_summary = cat_summary.sort_values('金额(EUR)', ascending=False)
                    st.dataframe(cat_summary, use_container_width=True)
            
            # 常规商品清单（可折叠）
            with st.expander(f"📦 常规商品清单（{len(regular_df)} 件，共 €{regular_total:.2f}）"):
                if regular_df.empty:
                    st.info("本月没有常规消费")
                else:
                    regular_display = regular_df[['name', 'category', 'purchaseDate', 'actualPrice', 'currency', 'eurValue']].copy()
                    regular_display = regular_display.sort_values('eurValue', ascending=False)
                    regular_display['purchaseDate'] = regular_display['purchaseDate'].dt.strftime('%Y-%m-%d')
                    regular_display['eurValue'] = regular_display['eurValue'].round(2)
                    regular_display['历史购买次数'] = regular_display['name'].apply(
                        lambda x: products_db.get(x, {}).get('purchaseCount', 1)
                    )
                    regular_display.columns = ['商品名称', '类别', '购买日期', '价格', '币种', '价值(EUR)', '历史购买次数']
                    st.dataframe(regular_display, use_container_width=True, hide_index=True)





# =========================
# 目标追踪页面
# =========================
elif page == "目标":
    st.header("🎯 消费目标追踪")
    st.caption("追踪饮食支出目标，支持多餐制计划")
    
    # ========== 目标设置区 ==========
    with st.expander("⚙️ 设置目标参数", expanded=False):
        col_s1, col_s2, col_s3 = st.columns(3)
        
        with col_s1:
            new_target_engel = st.slider(
                "目标恩格尔系数 (%)", 
                15, 60, 
                goals_db.get('target_engel', 35),
                help="食物支出占总支出的百分比"
            )
        
        with col_s2:
            new_target_meal_freq = st.number_input(
                "目标采购频次/月", 
                10, 60, 
                goals_db.get('target_meal_freq', 35),
                help="每月购买食物的次数（包括加餐）"
            )
        
        with col_s3:
            new_target_daily_food = st.number_input(
                "目标日均食物支出(EUR)", 
                5, 30, 
                goals_db.get('target_daily_food', 12),
                help="每天平均在食物上的花费"
            )
        
        # 食物类别设置
        st.markdown("**定义食物类别：**")
        available_categories = sorted(categories_db)
        default_food_cats = goals_db.get('food_categories', ['水果', '谷物', '饮料'])

        # 🔥 新增：过滤掉不存在的默认值
        valid_defaults = [cat for cat in default_food_cats if cat in available_categories]

        selected_food_categories = st.multiselect(
            "选择哪些类别计入食物支出",
            available_categories,
            default=valid_defaults  # 使用过滤后的默认值
        )
                
        if st.button("💾 保存目标设置"):
            goals_db['target_engel'] = new_target_engel
            goals_db['target_meal_freq'] = new_target_meal_freq
            goals_db['target_daily_food'] = new_target_daily_food
            goals_db['food_categories'] = selected_food_categories
            save_json(goals_db, GOALS_JSON)
            st.success("✅ 目标已保存！")
            time.sleep(1)
            st.rerun()
    
    # ========== 获取当前数据 ==========
    food_categories = goals_db.get('food_categories', ['水果', '谷物', '饮料'])
    target_engel = goals_db.get('target_engel', 35)
    target_meal_freq = goals_db.get('target_meal_freq', 35)
    target_daily_food = goals_db.get('target_daily_food', 12)
    
    # 当前月份数据
    all_expense = pd.concat([inventory_df, history_df, lost_df], ignore_index=True)
    
    if not all_expense.empty:
        all_expense['purchaseDate'] = pd.to_datetime(all_expense['purchaseDate'], errors='coerce')
        all_expense = all_expense.dropna(subset=['purchaseDate'])
        
        current_month = datetime.now().month
        current_year = datetime.now().year
        month_data = all_expense[
            (all_expense['purchaseDate'].dt.year == current_year) &
            (all_expense['purchaseDate'].dt.month == current_month)
        ].copy()
        
        if not month_data.empty:
            # 确保有eurValue
            if 'eurValue' not in month_data.columns:
                month_data['eurValue'] = month_data.apply(
                    lambda row: to_eur(row['actualPrice'], row['currency'], row['purchaseDate']),
                    axis=1
                )
            
            # 计算食物数据
            food_data = month_data[month_data['category'].isin(food_categories)]
            non_food_data = month_data[~month_data['category'].isin(food_categories)]
            
            total_expense = month_data['eurValue'].sum()
            food_expense = food_data['eurValue'].sum()
            
            current_engel = (food_expense / total_expense * 100) if total_expense > 0 else 0
            current_meal_count = len(food_data)
            
            days_passed = datetime.now().day
            current_daily = food_expense / days_passed if days_passed > 0 else 0
            
            # ========== 进度展示 ==========
            st.subheader(f"📊 本月进度（{current_year}-{current_month:02d}）")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                delta_engel = current_engel - target_engel
                st.metric(
                    "恩格尔系数", 
                    f"{current_engel:.1f}%",
                    delta=f"{delta_engel:+.1f}%",
                    delta_color="normal" if current_engel >= target_engel else "inverse"
                )
                progress1 = min(current_engel / target_engel, 1.0) if target_engel > 0 else 0
                st.progress(progress1)
                st.caption(f"目标: {target_engel}%")
            
            with col2:
                # 按月度天数调整目标
                days_in_month = pd.Period(f"{current_year}-{current_month}").days_in_month
                adjusted_target_freq = int(target_meal_freq * days_passed / days_in_month)
                
                delta_freq = current_meal_count - adjusted_target_freq
                st.metric(
                    "采购频次",
                    f"{current_meal_count}次",
                    delta=f"{delta_freq:+d}次"
                )
                progress2 = min(current_meal_count / adjusted_target_freq, 1.0) if adjusted_target_freq > 0 else 0
                st.progress(progress2)
                st.caption(f"目标: {adjusted_target_freq}次（截至今日）")
            
            with col3:
                delta_daily = current_daily - target_daily_food
                st.metric(
                    "日均食物支出",
                    f"€{current_daily:.2f}",
                    delta=f"€{delta_daily:+.2f}"
                )
                progress3 = min(current_daily / target_daily_food, 1.0) if target_daily_food > 0 else 0
                st.progress(progress3)
                st.caption(f"目标: €{target_daily_food:.2f}/天")
            
            # ========== 详细分析 ==========
            st.markdown("---")
            st.subheader("📈 详细分析")
            
            tab1, tab2, tab3 = st.tabs(["支出结构", "采购模式", "建议"])
            
            with tab1:
                col_a1, col_a2 = st.columns(2)
                
                with col_a1:
                    st.markdown("**食物支出占比**")
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=['食物', '非食物'],
                        values=[food_expense, total_expense - food_expense],
                        hole=0.4,
                        marker_colors=['rgba(251, 146, 60, 0.8)', 'rgba(200, 200, 200, 0.5)']
                    )])
                    fig_pie.update_layout(height=300, showlegend=True)
                    st.plotly_chart(fig_pie, use_container_width=True)
                
                with col_a2:
                    st.markdown("**食物类别分布**")
                    food_by_cat = food_data.groupby('category')['eurValue'].sum().sort_values(ascending=False)
                    fig_bar = go.Figure(data=[go.Bar(
                        x=food_by_cat.index,
                        y=food_by_cat.values,
                        marker_color='rgba(234, 88, 12, 0.8)',
                        text=[f"€{v:.1f}" for v in food_by_cat.values],
                        textposition='auto'
                    )])
                    fig_bar.update_layout(
                        height=300,
                        xaxis_title="类别",
                        yaxis_title="金额(EUR)",
                        showlegend=False
                    )
                    st.plotly_chart(fig_bar, use_container_width=True)
            
            with tab2:
                st.markdown("**本月采购时间线**")
                
                if not food_data.empty:
                    # 按日期分组
                    daily_food = food_data.groupby(food_data['purchaseDate'].dt.date).agg({
                        'eurValue': 'sum',
                        'name': 'count'
                    }).reset_index()
                    daily_food.columns = ['日期', '金额', '次数']
                    
                    fig_timeline = go.Figure()
                    fig_timeline.add_trace(go.Scatter(
                        x=daily_food['日期'],
                        y=daily_food['金额'],
                        mode='lines+markers',
                        name='日支出',
                        line=dict(color='rgb(234, 88, 12)', width=2),
                        marker=dict(size=8)
                    ))
                    
                    # 添加目标线
                    fig_timeline.add_hline(
                        y=target_daily_food, 
                        line_dash="dash", 
                        line_color="green",
                        annotation_text=f"目标: €{target_daily_food}/天"
                    )
                    
                    fig_timeline.update_layout(
                        height=300,
                        xaxis_title="日期",
                        yaxis_title="金额(EUR)",
                        hovermode='x unified'
                    )
                    st.plotly_chart(fig_timeline, use_container_width=True)
                    
                    # 显示详细记录
                    st.markdown("**详细采购记录**")
                    display_food = food_data[['purchaseDate', 'name', 'category', 'actualPrice', 'currency', 'eurValue']].copy()
                    display_food['purchaseDate'] = display_food['purchaseDate'].dt.strftime('%Y-%m-%d')
                    display_food = display_food.sort_values('purchaseDate', ascending=False)
                    display_food.columns = ['日期', '商品', '类别', '价格', '币种', '价值(EUR)']
                    st.dataframe(display_food, use_container_width=True, hide_index=True)
                else:
                    st.info("本月暂无食物采购记录")
            
            with tab3:
                st.markdown("**💡 个性化建议**")
                
                suggestions = []
                
                # 恩格尔系数建议
                if current_engel < target_engel * 0.8:
                    gap = target_engel - current_engel
                    needed_amount = (gap / 100) * total_expense
                    suggestions.append({
                        'type': '⚠️ 食物支出不足',
                        'detail': f'当前恩格尔系数 {current_engel:.1f}% 低于目标 {target_engel}%',
                        'action': f'建议增加约 €{needed_amount:.2f} 的食物采购'
                    })
                    
                    suggestions.append({
                        'type': '🛒 采购建议',
                        'detail': '增加高营养密度食物',
                        'action': '• Studentenfutter (坚果混合)\n• Käse (奶酪)\n• Vollkornbrot (全麦面包)\n• Griechischer Joghurt (希腊酸奶)'
                    })
                
                elif current_engel > target_engel * 1.2:
                    suggestions.append({
                        'type': '✅ 食物支出充足',
                        'detail': f'当前恩格尔系数 {current_engel:.1f}% 已超过目标',
                        'action': '保持当前采购习惯'
                    })
                
                # 采购频次建议
                if current_meal_count < adjusted_target_freq * 0.7:
                    suggestions.append({
                        'type': '📅 采购频次偏低',
                        'detail': f'本月已采购 {current_meal_count} 次，目标 {adjusted_target_freq} 次',
                        'action': '• 设置每周固定采购日（如周三、周六）\n• 准备"15分钟快速餐"清单降低决策疲劳'
                    })
                
                # 日均支出建议
                if current_daily < target_daily_food * 0.8:
                    suggestions.append({
                        'type': '💰 日均支出偏低',
                        'detail': f'当前日均 €{current_daily:.2f}，目标 €{target_daily_food:.2f}',
                        'action': '• 考虑在Mensa办充值卡\n• 增加ready-to-eat选项（Rewe/Edeka）'
                    })
                
                # 多餐制建议
                suggestions.append({
                    'type': '🍽️ 多餐制Tips',
                    'detail': '体重偏瘦适合5-6餐/天',
                    'action': '• 10:30 加餐（坚果+水果）\n• 16:00 加餐（酸奶+Müsli）\n• 睡前1小时可选补充\n• 准备"应急包"在书包'
                })
                
                # 显示建议
                for sug in suggestions:
                    with st.container():
                        st.markdown(f"**{sug['type']}**")
                        st.info(sug['detail'])
                        st.markdown(sug['action'])
                        st.markdown("---")
                
                # 德国超市推荐
                with st.expander("🏪 德国超市高性价比推荐"):
                    st.markdown("""
                    **高热量密度选择：**
                    - **Lidl Studentenfutter**: ~€1.5/100g, 500kcal+
                    - **Edeka Frischkäse**: ~€1/200g, 配Vollkornbrot
                    - **Rewe Bio Joghurt 3.8%**: 选全脂型
                    - **Aldi Nüsse**: 各类坚果性价比极高
                    - **Kaufland Tiefkühl-Lachs**: 冷冻三文鱼
                    
                    **便携加餐方案：**
                    - Banane (随处可买)
                    - Hartkäse小块包装
                    - Trockenfrüchte
                    - Riegel (能量棒，选高蛋白款)
                    """)
        
        else:
            st.info("本月暂无消费记录")
    
    else:
        st.info("暂无消费数据，请先进行入库")









# ==================== 桑基图分析 - 页面显示部分 ====================
# 这部分代码应该放在主程序的页面选择部分（elif page == "桑基图分析":）

elif page == "桑基":
    st.header("📊 消费流向桑基图")
    st.caption("三层流向分析：账户 → 来源 → 类型（线条粗细 = 金额）")
    
    # 配置文件路径
    PLATFORM_COLORS_JSON = DATA_DIR / "platform_colors.json"
    
    # 加载平台颜色配置
    platform_colors, config_errors = load_platform_colors(PLATFORM_COLORS_JSON)
    
    # 显示配置错误（如果有）
    if config_errors:
        with st.expander("⚠️ 配色文件问题", expanded=False):
            for error in config_errors[:5]:
                st.caption(error)
            if len(config_errors) > 5:
                st.caption(f"... 还有 {len(config_errors) - 5} 个问题")
    
    # ========== 强制重新加载CSV数据 ==========
    st.caption("🔄 正在加载最新数据...")
    inventory_df = force_load_csv_sankey(INVENTORY_CSV, inv_cols)
    history_df = force_load_csv_sankey(HISTORY_CSV, hist_cols)
    lost_df = force_load_csv_sankey(LOST_CSV, lost_cols)
    # sold_df = force_load_csv_sankey(SOLD_CSV, sold_cols)
    
    st.caption(f"✅ 已加载：inventory({len(inventory_df)}) + history({len(history_df)}) + lost({len(lost_df)})")
    
    # ========== 调试模式 ==========
    debug_mode = st.sidebar.checkbox("🔍 显示配色调试信息", value=False)
    
    if debug_mode:
        st.info(f"已加载 {len(platform_colors)} 个配色")
        
        # 显示所有配色
        with st.expander("📋 JSON中的所有配色", expanded=True):
            for key, value in sorted(platform_colors.items()):
                col1, col2, col3 = st.columns([1, 2, 3])
                with col1:
                    st.markdown(f'<div style="background-color: {value}; '
                              f'width: 50px; height: 25px; border: 1px solid black;"></div>', 
                              unsafe_allow_html=True)
                with col2:
                    st.code(key, language=None)
                with col3:
                    st.code(value, language=None)
    
    # ========== 合并数据 ==========
    # 注意：不包含 sold.csv，因为那是收入而非支出
    all_data = []
    for csv_file, df in [
        ('inventory.csv', inventory_df),  # 当前持有的物品
        ('history.csv', history_df),      # 历史购买记录
        ('lost.csv', lost_df)              # 丢失/损坏的物品
        # ❌ 不包含 sold.csv - 那是收回的钱，不是开支
    ]:
        if not df.empty:
            df_copy = df.copy()
            all_data.append(df_copy)
    
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        
        required_cols = ['category', 'source', 'account', 'eurValue', 'purchaseDate']
        if all(col in combined_df.columns for col in required_cols):
            combined_df = combined_df.dropna(subset=required_cols)
            combined_df['purchaseDate'] = pd.to_datetime(combined_df['purchaseDate'], errors='coerce')
            combined_df = combined_df.dropna(subset=['purchaseDate'])
            
            # ========== 调试：显示原始数据统计 ==========
            with st.expander("📊 原始数据统计", expanded=False):
                col_d1, col_d2, col_d3, col_d4 = st.columns(4)
                with col_d1:
                    st.metric("inventory", len(inventory_df))
                with col_d2:
                    st.metric("history", len(history_df))
                with col_d3:
                    st.metric("lost", len(lost_df))
                with col_d4:
                    st.metric("sold", len(sold_df))
                
                st.caption(f"合并后总记录数: {len(combined_df)}")
                
                if len(combined_df) > 0:
                    st.caption("最新的5条记录：")
                    st.dataframe(combined_df.tail(5)[['name', 'category', 'source', 'eurValue', 'purchaseDate']])
            
            # ========== 调试：显示数据中的实际平台 ==========
            if debug_mode:
                st.markdown("---")
                with st.expander("🏪 数据中的实际平台名称（source）", expanded=True):
                    actual_sources = sorted(combined_df['source'].dropna().unique().tolist())
                    st.caption(f"共 {len(actual_sources)} 个平台")
                    
                    st.markdown("**匹配测试：**")
                    for source in actual_sources[:20]:  # 只显示前20个
                        color, match_type, matched_key = get_platform_color(source, platform_colors)
                        
                        col1, col2, col3, col4 = st.columns([2, 1, 2, 3])
                        with col1:
                            st.text(source)
                        with col2:
                            if match_type == "精确匹配":
                                st.success("✅")
                            elif match_type == "模糊匹配":
                                st.info("🔍")
                            else:
                                st.warning("⚠️")
                        with col3:
                            st.caption(f"{match_type}: {matched_key if matched_key else '无'}")
                        with col4:
                            st.markdown(f'<div style="background-color: {color}; '
                                      f'width: 100px; height: 20px; border: 1px solid black;"></div>', 
                                      unsafe_allow_html=True)
            
            # 初始化筛选后的数据
            filtered_df = combined_df.copy()
            
            # ========== 数据筛选 ==========
            st.subheader("🎯 数据筛选")
            
            col_filter1, col_filter2 = st.columns(2)
            
            with col_filter1:
                category_filter = st.radio(
                    "类型显示模式",
                    ["显示全部", "只显示前N个", "手动选择"],
                    horizontal=True,
                    key="category_filter_mode"
                )
                
                if category_filter == "只显示前N个":
                    # 按金额排序
                    category_amounts = filtered_df.groupby('category')['eurValue'].sum().sort_values(ascending=False)
                    top_n_cat = st.slider("显示金额最高的前N个类型", 5, 20, 10, key="top_n_categories")
                    top_categories = category_amounts.head(top_n_cat).index.tolist()
                    filtered_df = filtered_df[filtered_df['category'].isin(top_categories)]
                    st.caption(f"✅ 显示前 {top_n_cat} 个类型（按金额）")
                elif category_filter == "手动选择":
                    all_categories = sorted(filtered_df['category'].unique().tolist())
                    selected_categories = st.multiselect(
                        "选择要显示的类型",
                        all_categories,
                        default=all_categories[:10] if len(all_categories) > 10 else all_categories,
                        key="selected_categories"
                    )
                    if selected_categories:
                        filtered_df = filtered_df[filtered_df['category'].isin(selected_categories)]
                        st.caption(f"✅ 已选择 {len(selected_categories)} 个类型")
            
            with col_filter2:
                source_filter = st.radio(
                    "来源显示模式",
                    ["显示全部", "只显示前N个"],
                    horizontal=True,
                    key="source_filter_mode"
                )
                
                if source_filter == "只显示前N个":
                    # 按金额排序
                    source_amounts = filtered_df.groupby('source')['eurValue'].sum().sort_values(ascending=False)
                    top_n_source = st.slider("显示金额最高的前N个来源", 5, 20, 10, key="top_n_sources")
                    top_sources = source_amounts.head(top_n_source).index.tolist()
                    filtered_df = filtered_df[filtered_df['source'].isin(top_sources)]
                    st.caption(f"✅ 显示前 {top_n_source} 个来源（按金额）")
            
            st.markdown("---")
            
            # ========== 时间筛选 ==========
            st.subheader("⏰ 时间筛选")
            
            col1, col2 = st.columns(2)
            
            with col1:
                time_range = st.selectbox(
                    "选择时间范围",
                    ["全部时间", "本年度", "本季度", "本月", "自定义"],
                    key="sankey_time_range"
                )
            
            with col2:
                if time_range == "自定义":
                    date_range = st.date_input(
                        "选择日期范围",
                        value=(
                            filtered_df['purchaseDate'].min().date(),
                            filtered_df['purchaseDate'].max().date()
                        ),
                        key="sankey_date_range"
                    )
            
            # 应用时间筛选
            if time_range == "本年度":
                current_year = datetime.now().year
                filtered_df = filtered_df[filtered_df['purchaseDate'].dt.year == current_year]
            elif time_range == "本季度":
                current_quarter = (datetime.now().month - 1) // 3 + 1
                current_year = datetime.now().year
                filtered_df = filtered_df[
                    (filtered_df['purchaseDate'].dt.year == current_year) &
                    (filtered_df['purchaseDate'].dt.quarter == current_quarter)
                ]
            elif time_range == "本月":
                current_month = datetime.now().month
                current_year = datetime.now().year
                filtered_df = filtered_df[
                    (filtered_df['purchaseDate'].dt.year == current_year) &
                    (filtered_df['purchaseDate'].dt.month == current_month)
                ]
            elif time_range == "自定义" and 'date_range' in locals():
                if len(date_range) == 2:
                    start_date = pd.Timestamp(date_range[0])
                    end_date = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1)
                    filtered_df = filtered_df[
                        (filtered_df['purchaseDate'] >= start_date) &
                        (filtered_df['purchaseDate'] < end_date)
                    ]
            
            # ========== 高级筛选 ==========
            with st.expander("🔍 高级筛选"):
                merge_small = st.checkbox(
                    "合并小类型（占比<1%）",
                    value=False,
                    key="merge_small_categories"
                )
                
                if merge_small:
                    total_amount = filtered_df['eurValue'].sum()
                    category_amounts = filtered_df.groupby('category')['eurValue'].sum()
                    small_categories = category_amounts[category_amounts / total_amount < 0.01].index.tolist()
                    
                    if small_categories:
                        filtered_df.loc[filtered_df['category'].isin(small_categories), 'category'] = '其他小类'
                        st.caption(f"✅ 已合并 {len(small_categories)} 个小类型")
            
            # ========== 数据概览 ==========
            st.subheader("📈 数据概览")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("总记录数", len(filtered_df))
            with col2:
                st.metric("总金额", f"€{filtered_df['eurValue'].sum():.2f}")
            with col3:
                st.metric("账户数", filtered_df['account'].nunique())
            with col4:
                st.metric("来源数", filtered_df['source'].nunique())
            
            # ========== 图表设置 ==========
            st.subheader("⚙️ 图表设置")
            col_opt1, col_opt2 = st.columns(2)
            
            with col_opt1:
                chart_height = st.select_slider(
                    "图表高度",
                    options=[600, 800, 1000, 1200, 1500],
                    value=1000,
                    key="chart_height"
                )
            
            with col_opt2:
                font_size = st.select_slider(
                    "字体大小",
                    options=[9, 10, 11, 12, 13, 14],
                    value=11,
                    key="font_size"
                )
            
            # ========== 生成桑基图 ==========
            if len(filtered_df) > 0:
                st.subheader("🌊 消费流向图")
                st.info("💡 线条粗细 = 金额大小 | 颜色 = 平台品牌色 | 黑色文字清晰显示")
                
                fig = create_sankey_diagram(filtered_df, platform_colors, chart_height, font_size)
                if fig:
                    render_sankey_with_highlight(fig, chart_height)
                    st.caption("💡 悬停节点高亮关联流向，其余淡化 | 点击右上角相机图标保存图片")
                
                # ========== 详细数据 ==========
                with st.expander("📊 查看详细数据"):
                    tab1, tab2, tab3 = st.tabs(["按账户", "按来源", "按类型"])
                    
                    with tab1:
                        account_stats = filtered_df.groupby('account').agg({
                            'eurValue': ['sum', 'count'],
                        }).round(2)
                        account_stats.columns = ['总金额(EUR)', '购买次数']
                        account_stats['金额占比%'] = (account_stats['总金额(EUR)'] / filtered_df['eurValue'].sum() * 100).round(1)
                        account_stats = account_stats.sort_values('总金额(EUR)', ascending=False)
                        st.dataframe(account_stats, use_container_width=True)
                    
                    with tab2:
                        source_stats = filtered_df.groupby('source').agg({
                            'eurValue': ['sum', 'count'],
                        }).round(2)
                        source_stats.columns = ['总金额(EUR)', '购买次数']
                        source_stats['金额占比%'] = (source_stats['总金额(EUR)'] / filtered_df['eurValue'].sum() * 100).round(1)
                        source_stats = source_stats.sort_values('总金额(EUR)', ascending=False)
                        st.dataframe(source_stats, use_container_width=True)
                    
                    with tab3:
                        category_stats = filtered_df.groupby('category').agg({
                            'eurValue': ['sum', 'count'],
                        }).round(2)
                        category_stats.columns = ['总金额(EUR)', '购买次数']
                        category_stats['金额占比%'] = (category_stats['总金额(EUR)'] / filtered_df['eurValue'].sum() * 100).round(1)
                        category_stats = category_stats.sort_values('总金额(EUR)', ascending=False)
                        st.dataframe(category_stats, use_container_width=True)
                
            else:
                st.warning("所选时间范围内没有数据")
        else:
            st.error(f"数据缺少必要列: {required_cols}")
    else:
        st.info("暂无购买记录数据")
























# =========================
# 指南页面
# =========================
elif page == "说明":
    st.header("✋🏻说明")
    st.markdown("_更新日期：02.11.2025_")
    st.markdown("""
        - 出售或删除功能解释：
            - 均摊或者垫付的情形：使用类型「垫付」，垫付只能通过结清（原来的出售）功能出库，出库商品不会被统计在桑基图或支出趋势图中。
            - 支付瓶子押金的情形：直接使用「删除」功能将相关交易删除，视为从未拥有该产品。
        - 支出趋势图解释：        
            - 报表页面的开支统计收集的数据来源包括：inventory.csv, history.csv 和 lost.csv ，因此，出售掉的商品不会被统计在内。
        - 订阅管理解释：
            - 使用订阅管理时，请在**付费日当天**记账，软件会将当天日期而非元数据中的日期视为付款日期处理。管理订阅的前提是知道什么时候自己付过款，不是么？如果软件有试用期，就先以0元价格入库。
            - 如果月底（如29,30,31日付款），推荐改为1日。
        - 桑基图说明：
            - 桑基图数据来源同样不包括sold；
        - SOLD特殊规则说明：
            - sold只负责结清垫付或者均摊的情形，不负责处理二手出售，出于维护考虑不修改文件名；
            - 如果以二手的形式出售产品，正常出库即可，利用率设置为（1-成色），即如果九五新出手，利用率写为5%。
        ***
        - 入库时，类型选择两个字的以便记忆。例如，避免将一些商品归类为谷物，另一些归类为谷物类。
        - 购买的无法转卖的虚拟类产品，仓储规则另行安排。
    """)

st.sidebar.markdown("---")
st.sidebar.caption("LaMer v1.50.20260314")
st.sidebar.caption("Seit 22. Sep. 2025")
st.sidebar.caption("Bundesrepublik Uta")
st.sidebar.caption("Claude Sonnet 4")
st.sidebar.caption("Claude Haiku 4.5")
st.sidebar.caption("Claude Opus 4.6 (Projekte)")
st.sidebar.caption("Python Streamlit")