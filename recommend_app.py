import pandas as pd
import streamlit as st
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
import folium
from streamlit_folium import folium_static
from folium.plugins import HeatMap
import unicodedata
import re

# ----------------- Load dữ liệu -----------------
df_sku = pd.read_excel("Mắt Kính Data.xlsx", sheet_name="SKU")
df_store = pd.read_excel("Mắt Kính Data.xlsx", sheet_name="Cửa hàng")

df_store[['Lat', 'Lon']] = df_store['Tọa độ'].str.strip().str.split(',', expand=True)
df_store['Lat'] = df_store['Lat'].astype(float)
df_store['Lon'] = df_store['Lon'].str.strip().astype(float)

df_sku.columns = df_sku.columns.str.strip()
df_sku['Price'] = df_sku['Price'].astype(float)

# ----------------- Giao diện người dùng -----------------
st.set_page_config(page_title="Đề xuất cửa hàng mắt kính", layout="centered")

st.markdown("<h1 style='text-align: center; color: #4CAF50;'>🕶️ Gợi ý cửa hàng mắt kính</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center;'>Tìm cửa hàng gần bạn nhất với nhiều sản phẩm trong tầm giá</p>", unsafe_allow_html=True)
st.markdown("---")

# --- Nhập thông tin ---
st.markdown("### 📍 Nhập thông tin")
min_price = st.number_input("Ngân sách tối thiểu (VND)", value=500000, step=50000, format="%d")
max_price = st.number_input("Ngân sách tối đa (VND)", value=1000000, step=50000, format="%d")
user_address = st.text_input("Địa chỉ hiện tại của bạn:", value="72 Lê Thánh Tôn, Quận 1, TP.HCM")

st.caption(f"💰 Ngân sách bạn chọn: **{min_price:,} VND** đến **{max_price:,} VND**")
st.markdown("<br>", unsafe_allow_html=True)

# ----------------- Nút xử lý -----------------
if st.button("🔍 Tìm cửa hàng phù hợp"):
    if not user_address or len(user_address.strip()) < 10:
        st.warning("❗ Vui lòng nhập địa chỉ chi tiết.")
    else:
        try:
            geolocator = Nominatim(user_agent="matkinh_app", timeout=10)

            def normalize_address(addr):
                addr = unicodedata.normalize('NFD', addr)
                addr = addr.encode('ascii', 'ignore').decode('utf-8')
                addr = re.sub(r'\b(Duong|Phuong|Quan)\b', '', addr, flags=re.IGNORECASE)
                addr = addr.replace("TP.HCM", "Ho Chi Minh City").replace("Hồ Chí Minh", "Ho Chi Minh City")
                addr = re.sub(r'\s+', ' ', addr).strip()
                return addr

            location = geolocator.geocode(user_address)
            if location is None:
                fallback = normalize_address(user_address)
                location = geolocator.geocode(fallback)

            if location is None:
                st.warning(f"❌ Không tìm được vị trí. Vui lòng kiểm tra lại địa chỉ.")
                st.stop()
            else:
                user_location = (location.latitude, location.longitude)
                st.success(f"📍 Đã xác định vị trí từ: `{user_address}`")

                def approx_equal(a, b, tol=0.0005):
                    return abs(a - b) < tol

                for _, row in df_store.iterrows():
                    if approx_equal(row["Lat"], user_location[0]) and approx_equal(row["Lon"], user_location[1]):
                        user_location = (row["Lat"], row["Lon"])
                        break

                df_sku_filtered = df_sku[(df_sku['Price'] >= min_price) & (df_sku['Price'] <= max_price)]
                sku_count = df_sku_filtered.groupby("Cửa hàng").size().reset_index(name="SKU phù hợp")
                df_merged = df_store.merge(sku_count, on="Cửa hàng", how="left").fillna(0)
                df_merged["SKU phù hợp"] = df_merged["SKU phù hợp"].astype(int)
                df_filtered = df_merged[df_merged["SKU phù hợp"] > 0].copy()

                if df_filtered.empty:
                    st.warning("⚠️ Không có cửa hàng nào có sản phẩm trong tầm giá bạn nhập.")
                else:
                    df_filtered["Khoảng cách (km)"] = df_filtered.apply(
                        lambda row: geodesic(user_location, (row["Lat"], row["Lon"])).km, axis=1
                    )
                    df_filtered["score_distance"] = 1 / (1 + df_filtered["Khoảng cách (km)"])
                    df_filtered["score_sku"] = df_filtered["SKU phù hợp"] / df_filtered["SKU phù hợp"].max()
                    df_filtered["Điểm tổng"] = (
                        df_filtered["score_distance"] * 0.4 + df_filtered["score_sku"] * 0.6
                    ).round(4)

                    best_store = df_filtered.sort_values("Điểm tổng", ascending=False).iloc[0]
                    st.markdown("### 🏆 Cửa hàng nên ghé thăm:")
                    st.write(f"**{best_store['Cửa hàng']}** — {best_store['SKU phù hợp']} SKU phù hợp | "
                             f"{best_store['Khoảng cách (km)']:.2f} km | "
                             f"Điểm ưu tiên: {best_store['Điểm tổng']}")

                    st.markdown("### 🗺️ Heatmap ưu tiên cửa hàng")
                    m = folium.Map(location=user_location, zoom_start=14)
                    folium.Marker(user_location, tooltip="📍 Vị trí của bạn", icon=folium.Icon(color='red')).add_to(m)

                    heat_data = [[row["Lat"], row["Lon"], row["Điểm tổng"]] for _, row in df_filtered.iterrows()]
                    HeatMap(heat_data, radius=20).add_to(m)

                    for _, row in df_filtered.iterrows():
                        folium.Marker(
                            location=(row["Lat"], row["Lon"]),
                            tooltip=f"{row['Cửa hàng']} | SKU: {row['SKU phù hợp']} | Điểm: {row['Điểm tổng']}"
                        ).add_to(m)

                    folium_static(m)

                    st.markdown("### 📋 Danh sách cửa hàng gợi ý")
                    st.dataframe(
                        df_filtered[["Cửa hàng", "SKU phù hợp", "Khoảng cách (km)", "Điểm tổng"]]
                        .sort_values("Điểm tổng", ascending=False)
                        .reset_index(drop=True)
                    )

        except Exception as e:
            st.error(f"❌ Lỗi khi xử lý: {e}")