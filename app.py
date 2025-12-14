import streamlit as st
import pandas as pd
from lunar_python import Lunar, Solar
import os
import json
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- 1. 頁面設定 ---
st.set_page_config(
    page_title="2026 丙午年・紫微斗數運勢詳批", 
    page_icon="🔮", 
    layout="centered"
)

# 隱藏 Streamlit 原生介面 CSS
hide_streamlit_style = """
<style>
    header[data-testid="stHeader"] {display: none !important;}
    [data-testid="stToolbar"] {display: none !important;}
    .stAppDeployButton {display: none !important;}
    footer {display: none !important;}
    .block-container {padding-top: 1rem !important;}
    
    .locked-box {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        text-align: center;
        border: 2px dashed #a1a1a1;
        margin: 20px 0;
    }
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# --- 2. 載入 CSV 資料 ---
@st.cache_data
def load_data():
    if not os.path.exists("2026_data.csv"):
        return None
    try:
        df = pd.read_csv("2026_data.csv")
        df['Star_ID'] = df['Star_ID'].astype(str).str.strip()
        return df
    except:
        return None

df_fortune = load_data()

# --- 3. 核心排盤演算法 ---
def get_bazi_ju(year_gan_idx, life_branch_idx):
    start_gan = (year_gan_idx % 5) * 2 + 2 
    offset = (life_branch_idx - 2) % 12
    life_gan_idx = (start_gan + offset) % 10
    g_val = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5][life_gan_idx]
    z_map = {0:0, 1:0, 6:0, 7:0, 2:1, 3:1, 8:1, 9:1, 4:2, 5:2, 10:2, 11:2}
    z_val = z_map[life_branch_idx]
    sum_val = g_val + z_val
    if sum_val > 5: sum_val -= 5
    ju_map = {1:4, 2:2, 3:6, 4:5, 5:3}
    return ju_map[sum_val]

def get_ziwei_pos(lunar_day, ju):
    q = lunar_day // ju
    r = lunar_day % ju
    if r == 0:
        pos = (2 + q - 1) % 12
    else:
        base_pos = (2 + (q + 1) - 1) % 12
        diff = ju - r
        if diff % 2 != 0:
            pos = (base_pos - diff) % 12
        else:
            pos = (base_pos + diff) % 12
    return pos

def get_true_star_in_wu(year, month, day, hour_idx):
    solar = Solar.fromYmdHms(year, month, day, 0, 0, 0)
    lunar = solar.getLunar()
    l_month = lunar.getMonth()
    if l_month < 0: l_month = abs(l_month)
    l_day = lunar.getDay()
    gan_map = {"甲":0, "乙":1, "丙":2, "丁":3, "戊":4, "己":5, "庚":6, "辛":7, "壬":8, "癸":9}
    l_year_gan = gan_map.get(lunar.getYearGan(), 0)

    life_idx = (2 + (l_month - 1) - hour_idx) % 12
    ju = get_bazi_ju(l_year_gan, life_idx)
    zw_pos = get_ziwei_pos(l_day, ju)
    tf_pos = (4 - zw_pos) % 12
    
    zw_stars = {0: "紫微", 1: "天機", 3: "太陽", 4: "武曲", 5: "天同", 8: "廉貞"}
    tf_stars = {0: "天府", 1: "太陰", 2: "貪狼", 3: "巨門", 4: "天相", 5: "天梁", 6: "七殺", 10: "破軍"}
    
    target_stars = []
    diff_zw = (zw_pos - 6) % 12
    if diff_zw in zw_stars: target_stars.append(zw_stars[diff_zw])
    diff_tf = (6 - tf_pos) % 12
    if diff_tf in tf_stars: target_stars.append(tf_stars[diff_tf])
        
    if not target_stars:
        opp_stars = []
        diff_zw_opp = (zw_pos - 0) % 12
        if diff_zw_opp in zw_stars: opp_stars.append(zw_stars[diff_zw_opp])
        diff_tf_opp = (0 - tf_pos) % 12
        if diff_tf_opp in tf_stars: opp_stars.append(tf_stars[diff_tf_opp])
        return "+".join(opp_stars)
        
    if len(target_stars) > 1:
        if "紫微" in target_stars: 
            target_stars.sort(key=lambda x: x != "紫微")
        elif "廉貞" in target_stars and "貪狼" in target_stars: 
            return "廉貞+貪狼"
            
    return "+".join(target_stars)

# --- 4. Google Sheets 連線 ---

def get_google_sheet_connection():
    scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
    
    if os.path.exists("google_key.json"):
        creds = ServiceAccountCredentials.from_json_keyfile_name('google_key.json', scope)
    else:
        key_dict = dict(st.secrets["gcp_service_account"])
        if "private_key" in key_dict:
            pk = key_dict["private_key"]
            pk = pk.replace("\\n", "\n")
            if "-----BEGIN PRIVATE KEY-----" not in pk:
                pk = "-----BEGIN PRIVATE KEY-----\n" + pk
            if "-----END PRIVATE KEY-----" not in pk:
                pk = pk + "\n-----END PRIVATE KEY-----"
            key_dict["private_key"] = pk
        creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
    
    client = gspread.authorize(creds)
    
    # === ⚠️ 請在此填入 Google Sheet ID ===
    sheet_id = '1CTm-U3IsDy-Z-oc5eVWY__G22XStDV7BvSQ5bhIDCu0' 
    # ==================================
    
    if '1CTm-U3IsDy-Z-oc5eVWY__G22XStDV7BvSQ5bhIDCu0' in sheet_id:
         return client.open("2026_Ledger").sheet1
    else:
         return client.open_by_key(sheet_id).sheet1

def check_license_binding_cloud(license_key, user_birth_id):
    try:
        sheet = get_google_sheet_connection()
        records = sheet.get_all_records()
        ledger = {}
        for row in records:
            k = str(row.get('license_key', row.get('License_Key', ''))).strip()
            v = str(row.get('user_birth_id', '')).strip()
            if k: ledger[k] = v
        
        input_key = str(license_key).strip()
        if input_key in ledger:
            saved_id = ledger[input_key]
            if not saved_id or saved_id == "":
                # 只有當 user_birth_id 真的有值時才進行綁定
                if user_birth_id and user_birth_id != "":
                    cell = sheet.find(input_key)
                    sheet.update_cell(cell.row, 2, user_birth_id)
                    sheet.update_cell(cell.row, 3, str(datetime.now()))
                    return True, "✅ 序號首次啟用成功！"
                else:
                    return True, "⏳ 序號有效！請點擊下方按鈕綁定生日。" # 特殊狀態：有望遠鏡但還沒綁定
            elif saved_id == user_birth_id:
                return True, "歡迎回來！驗證成功。"
            else:
                return False, "❌ 此序號已被其他生日綁定，無法使用。"
        else:
            return False, "❌ 無效的序號。"
    except Exception as e:
        return False, f"連線錯誤: {str(e)}"

# --- 5. 文字排版 ---
def format_text(text):
    if pd.isna(text): return ""
    text = str(text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = text.replace("\n", "<br>") 
    return text

def show_footer():
    st.markdown("---")
    st.markdown(
        """<div style="text-align: center; color: #888888; font-size: 0.9em;">
            本測算系統由 <a href="https://afei-tw.com/" target="_blank" style="color:#FF4B4B;text-decoration:none;">阿飛．不會飛</a> 提供
        </div>""", unsafe_allow_html=True)

# --- 6. 主程式介面 ---

if "calculated" not in st.session_state:
    st.session_state.calculated = False
if "unlocked" not in st.session_state:
    st.session_state.unlocked = False
if "user_birth_id" not in st.session_state:
    st.session_state.user_birth_id = ""

# [新增] 自動抓取網址參數 (Auto-Detect URL Params)
# 這段代碼會去抓 ?license_key=xxxx
query_params = st.query_params
auto_license_key = query_params.get("license_key", None)

# === 狀態 A: 輸入資料頁 ===
if not st.session_state.calculated:
    st.title("2026 丙午年・紫微斗數運勢詳批")
    if os.path.exists("banner.jpg"):
        st.image("banner.jpg", use_container_width=True)
    
    # [新增] 如果網址帶有序號，顯示歡迎訊息
    if auto_license_key:
        st.success("🎉 付款成功！系統已自動帶入您的解鎖序號，請輸入生日以完成綁定。")
    else:
        st.info("👇 請輸入出生資料，免費預覽您的 2026 運勢格局")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1: b_year = st.number_input("出生年 (西元)", 1940, 2025, 1990)
        with col2: b_month = st.selectbox("出生月", range(1, 13), index=5)
        col3, col4 = st.columns(2)
        with col3: b_day = st.selectbox("出生日", range(1, 32), index=14)
        with col4:
            hours_map = {"子 (23-01)":0,"丑 (01-03)":1,"寅 (03-05)":2,"卯 (05-07)":3,"辰 (07-09)":4,"巳 (09-11)":5,"午 (11-13)":6,"未 (13-15)":7,"申 (15-17)":8,"酉 (17-19)":9,"戌 (19-21)":10,"亥 (21-23)":11}
            b_hour_str = st.selectbox("出生時辰", list(hours_map.keys()), index=6)
            b_hour = hours_map[b_hour_str]

        if st.button("🔥 開始分析運勢", type="primary", use_container_width=True):
            st.session_state.b_year = b_year
            st.session_state.b_month = b_month
            st.session_state.b_day = b_day
            st.session_state.b_hour = b_hour
            st.session_state.user_birth_id = f"{b_year}-{b_month}-{b_day}-{b_hour}"
            st.session_state.calculated = True
            
            # [新增] 如果有自動序號，直接在這裡嘗試解鎖
            if auto_license_key:
                # 這裡只要先進入結果頁，結果頁會自動處理驗證
                pass 
            
            st.rerun()
    show_footer()

# === 狀態 B: 結果展示頁 ===
else:
    if df_fortune is None:
        st.error("❌ 系統錯誤：找不到資料庫檔案。")
    else:
        b_year = st.session_state.b_year
        b_month = st.session_state.b_month
        b_day = st.session_state.b_day
        b_hour = st.session_state.b_hour
        user_birth_id = st.session_state.user_birth_id

        star_name = get_true_star_in_wu(b_year, b_month, b_day, b_hour)
        res = df_fortune[df_fortune['Star_ID'] == star_name]
        if res.empty and "+" in star_name:
            p1 = star_name.split("+")[0]
            res = df_fortune[df_fortune['Star_ID'] == p1]

        if not res.empty:
            data = res.iloc[0]
            
            # --- [新增] 自動解鎖邏輯 ---
            # 如果還沒解鎖，但網址有序號，則自動執行一次驗證
            if not st.session_state.unlocked and auto_license_key:
                with st.spinner("正在為您自動啟用完整報告..."):
                    is_valid, msg = check_license_binding_cloud(auto_license_key, user_birth_id)
                if is_valid:
                    st.session_state.unlocked = True
                    st.toast("✅ 自動解鎖成功！", icon="🎉")
                    # 不用 rerun，直接往下跑就會顯示解鎖內容
                else:
                    st.error(msg)
            # ------------------------

            st.title("2026 流年運勢分析報告")
            st.success(f"您的流年命宮主星：【{star_name}】")
            c1, c2 = st.columns([1,2])
            with c1: st.metric("年度運勢評分", f"{data['Score']} 分")
            with c2: st.info(f"✨ 年度金句：{data['Summary']}")
            
            st.markdown("### 📜 年度總運勢 (免費試閱)")
            st.markdown(format_text(data['Content_General']), unsafe_allow_html=True)
            st.divider()

            if not st.session_state.unlocked:
                st.markdown(
                    """
                    <div class="locked-box">
                        <h3>🔒 進階運勢報告已鎖定</h3>
                        <p style="color: #666;">付費解鎖後，您將獲得完整流年詳批...</p>
                    </div>
                    """, unsafe_allow_html=True
                )
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("❌ **感情運勢** (隱藏)")
                    st.markdown("❌ **事業發展** (隱藏)")
                with col2:
                    st.markdown("❌ **財運分析** (隱藏)")
                    st.markdown("❌ **流月運勢** (隱藏)")
                st.write("") 

                with st.container(border=True):
                    st.markdown("#### 🚀 立即解鎖完整報告")
                    buy_link = "https://afei-tw.com/checkout/?add-to-cart=2026-fortune-teller-ziwei" 
                    st.link_button("💳 只需298元解鎖！前往取得序號", buy_link, type="primary", use_container_width=True)
                    st.markdown("---")
                    
                    st.caption("已有序號？請在下方輸入：")
                    c_input, c_btn = st.columns([3,1])
                    # 如果有自動序號但驗證失敗(例如已綁定別人)，至少把它填在格子裡方便修改
                    default_key = auto_license_key if auto_license_key else ""
                    input_key = c_input.text_input("License Key", value=default_key, placeholder="例如: 2026-XXXX-XXXX", label_visibility="collapsed")
                    
                    if c_btn.button("解鎖", type="secondary"):
                        with st.spinner("驗證中..."):
                            is_valid, msg = check_license_binding_cloud(input_key, user_birth_id)
                        if is_valid:
                            st.session_state.unlocked = True
                            st.rerun()
                        else:
                            st.error(msg)
            else:
                st.balloons()
                st.success("🎉 報告已完整解鎖！")
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["💘 感情", "💼 事業", "💰 財運", "🏥 健康", "📅 流月"])
                with tab1: st.markdown(format_text(data.get('Content_Love')), unsafe_allow_html=True)
                with tab2: st.markdown(format_text(data.get('Content_Career')), unsafe_allow_html=True)
                with tab3: st.markdown(format_text(data.get('Content_Fortune')), unsafe_allow_html=True)
                with tab4: st.markdown(format_text(data.get('Content_Health')), unsafe_allow_html=True)
                with tab5: st.markdown(format_text(data.get('Content_Monthly')), unsafe_allow_html=True)
                st.markdown("---")
                if st.button("🔄 重新測算"):
                    st.session_state.calculated = False
                    st.session_state.unlocked = False
                    st.rerun()

    show_footer()