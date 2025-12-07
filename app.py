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
    # 這裡拆成兩行寫，避免斷行錯誤
    spreadsheet = client.open("2026_Ledger")
    return spreadsheet.sheet1

def check_license_binding_cloud(license_key, user_birth_id):
    try:
        sheet = get_google_sheet_connection()
        records = sheet.get_all_records()
        
        # === 診斷資訊 (讀取成功會顯示) ===
        if len(records) > 0:
            st.info("💡 系統診斷：資料庫連線成功！")
        # =============================
        
        ledger = {}
        for row in records:
            k = str(row.get('license_key', row.get('License_Key', ''))).strip()
            v = str(row.get('user_birth_id', '')).strip()
            if k:
                ledger[k] = v
        
        input_key = str(license_key).strip()

        if not ledger and len(records) > 0:
             st.error("❌ 嚴重錯誤：找不到 license_key 欄位！請檢查 Google Sheet 標題。")
             return False, "資料庫欄位錯誤"

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
        """<div style="text-align: center; color: #888888; font-size: 0.8em; padding: 10px;">
            🔒 隱私聲明：本系統不會永久儲存您的個資，請安心使用。
        </div>""", 
        unsafe_allow_html=True
    )

# --- 6. 主程式介面 ---

if "calculated" not in st.session_state:
    st.session_state.calculated = False
if "unlocked" not in st.session_state:
    st.session_state.unlocked = False
if "user_birth