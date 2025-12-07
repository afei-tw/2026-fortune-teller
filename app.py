import streamlit as st

st.title("✅ 系統測試模式")
st.write("如果看得到這行字，代表主機是好的！")

# 測試套件有沒有裝好
try:
    import gspread
    st.success("1. gspread 套件：安裝成功")
except Exception as e:
    st.error(f"1. gspread 套件：失敗 ({e})")

# 測試金鑰讀不讀得到
try:
    # 嘗試讀取 Secrets
    project_id = st.secrets["gcp_service_account"]["project_id"]
    st.success(f"2. Secrets 金鑰：讀取成功 (ID: {project_id})")
except Exception as e:
    st.error(f"2. Secrets 金鑰：失敗 (格式可能有錯) -> {e}")
