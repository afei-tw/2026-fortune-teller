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
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    
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
    
    # === ⚠️ 請務必在此填入你的 Google Sheet ID ===
    sheet_id = '1aBcD-xYz12345...' # (請填入你之前複製的 ID)
    # ==========================================
    
    # 若 ID 仍為預設值，嘗試 fallback (但建議填 ID)
    if '1aBcD' in sheet_id: 
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
            if k:
                ledger[k] = v
        
        input_key = str(license_key).strip()

        if input_key in ledger:
            saved_id = ledger[input_key]
            
            if not saved_id or saved_id == "":
                cell = sheet.find(input_key)
                sheet.update_cell(cell.row, 2, user_birth_id)
                sheet.update_cell(cell.row, 3, str(datetime.now()))
                return True, "✅ 序號首次啟用成功！"
            
            elif saved_id == user_birth_id:
                return True, "歡迎回來！驗證成功。"
            
            else:
                return False, "❌ 此序號已綁定其他生日，無法用於此命盤。"
        else:
            return False, f"❌ 無效的序號 ({input_key})，未在資料庫中找到。"
            
    except Exception as e:
        return False, f"連線錯誤: {str(e)}"

# --- 5. 文字排版 ---
def format_text(text):
    if pd.isna(text): return "（此欄位無資料）"
    text = str(text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = text.replace("\n", "<br>") 
    if "✓" in text:
        text = text.replace("✓", "<br><br>✓ ")
    return text

def show_footer():
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align: center; color: #888888; font-size: 0.9em; line-height: 1.8;">
            本測算系統由 <a href="https://afei-tw.com/" target="_blank" style="color: #FF4B4B; text-decoration: none; font-weight: bold;">阿飛．不會飛</a> 提供<br>
            <span style="font-size: 0.8em;">🔒 隱私聲明：本系統不會永久儲存您的個資，請安心使用。</span>
        </div>
        """, 
        unsafe_allow_html=True
    )

# --- 6. 主程式介面 ---

if "calculated" not in st.session_state:
    st.session_state.calculated = False
if "unlocked" not in st.session_state:
    st.session_state.unlocked = False
if "user_birth_id" not in st.session_state:
    st.session_state.user_birth_id = ""

# === 狀態 A: 首頁 ===
if not st.session_state.calculated:
    st.title("2026 丙午年・紫微斗數運勢詳批")
    if os.path.exists("banner.jpg"):
        st.image("banner.jpg", use_container_width=True)
    
    st.markdown("""
    ### 🐎 2026 火馬奔騰，您的運勢準備好了嗎？
    
    2026年是天干地支皆屬火的「**丙午年**」，又被稱為「**火馬年**」。
    這意味著整體大環境將充滿**變動、爆發與蛻變**的能量。
    
    運勢強時如何乘勢而為？運勢弱時如何持盈保泰？
    這將是您在充滿變革的火馬年中，掌握先機的重要關鍵。
    
    ---
    
    #### 【本流年測算特色】
    
    ✅ **全方位解析** 針對財運、事業、感情、健康四大運勢，提供具體建議。

    ✅ **個人化命盤** 不講空泛的大道理，只針對您的命盤給出解方。

    ✅ **關鍵月份提醒** 告訴您哪個月該衝、哪個月該守，精準掌握運勢起伏。

    ---
    """, unsafe_allow_html=True)
    
    st.success("👇 **請在此輸入您的出生資料，立即開啟流年卷軸**")
    
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            b_year = st.number_input("出生年 (西元)", 1940, 2025, 1990)
        with col2:
            b_month = st.selectbox("出生月", range(1, 13), index=5)
        col3, col4 = st.columns(2)
        with col3:
            b_day = st.selectbox("出生日", range(1, 32), index=14)
        with col4:
            hours_map = {
                "子 (23-01)": 0, "丑 (01-03)": 1, "寅 (03-05)": 2, "卯 (05-07)": 3,
                "辰 (07-09)": 4, "巳 (09-11)": 5, "午 (11-13)": 6, "未 (13-15)": 7,
                "申 (15-17)": 8, "酉 (17-19)": 9, "戌 (19-21)": 10, "亥 (21-23)": 11
            }
            b_hour_str = st.selectbox("出生時辰", list(hours_map.keys()), index=6)
            b_hour = hours_map[b_hour_str]

        if st.button("🔥 開始排盤測算", type="primary", use_container_width=True):
            st.session_state.b_year = b_year
            st.session_state.b_month = b_month
            st.session_state.b_day = b_day
            st.session_state.b_hour = b_hour
            st.session_state.user_birth_id = f"{b_year}-{b_month}-{b_day}-{b_hour}"
            st.session_state.calculated = True
            st.session_state.unlocked = False 
            st.rerun()
    
    show_footer()

# === 狀態 B: 結果頁 ===
else:
    if df_fortune is None:
        st.error("❌ 系統錯誤：找不到資料庫檔案 `2026_data.csv`。")
        if st.button("返回首頁"):
            st.session_state.calculated = False
            st.rerun()
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
                st.caption(f"💡 您的格局為【{star_name}】，顯示主星【{p1}】運勢。")

        if not res.empty:
            data = res.iloc[0]
            
            st.title("2026 丙午年・紫微斗數運勢詳批")
            st.markdown(f"### 您的流年命宮主星：【{star_name}】")
            
            col1, col2 = st.columns([1, 2])
            with col1:
                st.metric("年度運勢評分", f"{data['Score']} 分")
            with col2:
                st.markdown("##### ✨ 你的年度金句") 
                st.info(f"{data['Summary']}")
                
            st.divider()
            st.subheader(f"📜 {data['Title']}")
            st.markdown(format_text(data['Content_General']), unsafe_allow_html=True)
            st.divider()
            
            if not st.session_state.unlocked:
                container = st.container(border=True)
                container.markdown("### 🔒 解鎖完整流年報告")
                container.write("付費解鎖後，您將看到以下詳細內容：")
                
                c1, c2, c3, c4, c5 = container.columns(5)
                c1.markdown("❤️ **感情運**")
                c2.markdown("💼 **事業運**")
                c3.markdown("💰 **財運**")
                c4.markdown("🏥 **健康運**") 
                c5.markdown("📅 **流月運**")
                
                container.markdown("---")
                
                # [修正] 導購按鈕區塊 - 移除欄位限制，全寬顯示
                st.link_button("💳 只需298元解鎖！前往取得序號", "https://afei-tw.com/product/2026-fortune-teller-ziwei/", type="secondary", use_container_width=True)
                
                container.caption("⚠️ 注意：序號一經使用即綁定此生日，無法轉讓給他人使用。")
                col_input, col_btn = container.columns([3, 1])
                input_key = col_input.text_input("請輸入解鎖序號", placeholder="例如: 2026-XXXX-XXXX", label_visibility="collapsed")
                
                if col_btn.button("立即解鎖", type="primary"):
                    with st.spinner("正在連線資料庫驗證..."):
                        is_valid, msg = check_license_binding_cloud(input_key, user_birth_id)
                    
                    if is_valid:
                        st.session_state.unlocked = True
                        st.rerun()
                    else:
                        container.error(msg)
            else:
                st.success("🎉 已解鎖完整報告！建議您截圖保存。")
                tab1, tab2, tab3, tab4, tab5 = st.tabs(["💘 感情運", "💼 事業運", "💰 財運", "🏥 健康運", "📅 流月運勢"])
                
                with tab1:
                    st.markdown("### 感情與人際")
                    st.markdown(format_text(data.get('Content_Love')), unsafe_allow_html=True)
                with tab2:
                    st.markdown("### 事業與工作")
                    st.markdown(format_text(data.get('Content_Career')), unsafe_allow_html=True)
                with tab3:
                    st.markdown("### 財運與投資")
                    st.markdown(format_text(data.get('Content_Fortune')), unsafe_allow_html=True)
                with tab4: 
                    st.markdown("### 🏥 健康與平安")
                    st.markdown(format_text(data.get('Content_Health')), unsafe_allow_html=True)
                with tab5:
                    st.markdown("### 2026 流月運勢地圖")
                    st.markdown(format_text(data.get('Content_Monthly')), unsafe_allow_html=True)
                
                st.markdown("---")
                if st.button("🔄 重新測算 (輸入新生日需新序號)", use_container_width=True):
                    st.session_state.calculated = False
                    st.session_state.unlocked = False
                    st.rerun()
            show_footer()
        else:
            st.error(f"資料庫中找不到【{star_name}】的資料。")
            if st.button("返回首頁"):
                st.session_state.calculated = False
                st.rerun()