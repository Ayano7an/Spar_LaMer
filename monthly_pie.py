import pandas as pd
from pathlib import Path
import matplotlib.pyplot  as plt 

# === CONFIG FONT FAMILY TO DISPLAY HANZI ===
plt.rcParams['font.family'] = 'BiaukaiHK' # for macOS only
plt.rcParams['axes.unicode_minus'] = False

# === CONFIG INPUT & OUTPUT PATH === 
input_dir = Path("lamer_data")
output_dir = Path("lamer_report")
output_dir.mkdir(parents=True, exist_ok=True)

# === INPUT MULTIPLE CSV FILES  --> INTO PYTHON ===
csv_list = ['history.csv','sold.csv','lost.csv', 'inventory.csv']
dataframes= [] # 设置存储多个数据框的列表 

# 文件内容被转为df对象，存入一个名为dataframes的列表
for file_path in input_dir.glob("*.csv"):
    if file_path.name in csv_list:
        df = pd.read_csv(file_path)
        dataframes.append(df)
print(f"处理完成，已经读取{len(dataframes)}个表格，并将其df化后存入列表。")

# === EXTRACT DATA FROM MULTIPLE DFs --> INTO ONE SINGLE DF ===
# 从上面列表中的诸多表格中，提取指定的三列数据，然后横向相连，当然，这些结果要存储在一个新的df里。

combined_df = pd.DataFrame() 
columns_to_extract = [ 'purchaseDate' , 'category',  'eurValue'] 
for df in dataframes:
    selected_col = df[columns_to_extract]
    combined_df = pd.concat([combined_df,selected_col], ignore_index=True)
print(f"处理完成，已经将{len(dataframes)}个表格，合并为一个数据框，前五行数据预览。\n")
print(combined_df.head())

# === 准备开支分布扇形图的数据 === 

def expensePiechart(df, month):
    # 筛选特定月份
    monthly_data = df[df['purchaseDate'].str[:7] == month ] # ! 记得先字符串化再切片

    # 按月别汇总
    category_sum = monthly_data.groupby('category')['eurValue'].sum()  # 汇总(每个类别)的.总[金额]

    # 支出总额降序排序
    category_sum = category_sum.sort_values(ascending=False)

    return category_sum 
print("扇形月度开支分布数据已就绪！")

# === 绘制扇形图 === 

# 获取指定月份的分类开支数据表
month_number = input("输入月份数据，格式'YYYY-MM'：")
result = expensePiechart(combined_df, month_number)

# 自定义autopct函数来显示金额
def make_autopct(values):
    def my_autopct(pct):
        total = sum(values)
        val = pct * total / 100.0
        return f'€{val:.2f} ({pct:.1f}%)' if pct > 4 else ''  #显示金额和百分比的阈值设置
    return my_autopct


# 显示开支占比超过5%的分类名称
percentages = result / result.sum() * 100
labels = [name if pct > 1 else '' for name, pct in zip(result.index, percentages)] #显示分类名称的阈值设置

result.plot.pie(
    autopct=make_autopct(result),  # 使用自定义函数显示金额
    startangle=90,
    labels=labels  # 启用labels过滤
) 

plt.ylabel("")
plt.xlabel(f"{month_number} Expense Distribution")

# 输出图片
output_path = output_dir / f'expense_pie_{month_number}.png'
plt.savefig(output_path)
print(f"扇形图已经保存至LaMer报告目录{output_dir}中！")