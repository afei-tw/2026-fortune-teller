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
    try:
        if not os.path.exists("2026_data.csv"):
            return None
        df = pd.read_csv("2026_data.csv")
        df['Star_ID'] = df['Star_ID'].astype(str).str.strip()
        return df
    except Exception as e:
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
    try:
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
            if "紫微" in target_stars: target_stars.sort(key=lambda x: x != "紫微")
            elif "廉貞" in target_stars and "貪狼" in target_stars: return "廉貞+貪狼"