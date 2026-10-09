import pandas as pd
import streamlit as st
import altair as alt
import io
from pathlib import Path

st.set_page_config(
    page_title="Goc Registration and Attendance Dashboard",
    page_icon=":chart",
    layout="wide"
)

CSV_path = Path(__file__).parent / "Workin.csv"
Required = ["Full Name", "Church", "Phone", "Email", "School", "Zone", "State", "Attendance Status"]
Status = "Attendance Status"         
Missing = ["", "null", "unknown", "n/a", "na", "-", "nan", "none", "nil"]
S_Color = alt.Scale(
    domain=["Present", "Not Checked In"], range=["#2e7d32", "#e57373"]
)


def clean_text(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.replace(r"\s+", " ", regex=True)  
    s = s.str.strip().str.strip(".,;:").str.strip()
    return s.where(~s.str.lower().isin(Missing), "Unknown")         


def harmonise(s: pd.Series) -> pd.Series:
    key = s.str.lower()
    display = s.groupby(key).agg(lambda x: x.value_counts().index[0])
    return key.map(display)


@st.cache_data
def load_data(raw: bytes) -> pd.DataFrame:
    data1 = pd.read_csv(io.BytesIO(raw), dtype=str)
    data1.columns = data1.columns.str.strip()
    missing = [c for c in Required if c not in data1.columns]
    if missing:
        raise ValueError(f"CSV is missing: {', '.join(missing)}")
    for col in ["Full Name", "Church", "School", "Zone", "State", Status, "Email"]:
        data1[col] = clean_text(data1[col])
    for col in ["Church", "School", "State"]:
        data1[col] = harmonise(data1[col])
    data1["Phone"] = data1["Phone"].fillna("").str.strip()
    data1["Present"] = data1[Status].eq("Present")
    data1["Duplicate Name"] = data1["Full Name"].str.lower().duplicated(keep=False)
    return data1


def Zone_order(values) -> list:
    return sorted(values, key=lambda z: (0, int(z)) if z.isdigit() else (1, 0))


def stacked_bar(data1, field, order=None, height=None):
    counts = data1.groupby([field, Status]).size().reset_index(name="Count")
    if order is None:
        order = data1[field].value_counts().index.tolist()      
    return (
        alt.Chart(counts, height=height or max(220, 26 * len(order))).mark_bar().encode(
            y=alt.Y(f"{field}:N", sort=order, title=None),
            x=alt.X("Count:Q", title="People"),
            color=alt.Color(f"{Status}:N", scale=S_Color, title=None,
                            legend=alt.Legend(orient="bottom")),
            tooltip=[field, Status, "Count"],
        )
    )


def top_N_chart(data1,field,n,include_unknown):
    d=data1 if include_unknown else data1[data1[field]!="Unknown"]
    top=d[field].value_counts().head(n).index.tolist()
    return stacked_bar(d[d[field].isin(top)],field,order=top)


st.title("Goc Registration Dashboard")

if not CSV_path.exists() :
    st.error(f"No CSV file found{{CSV_path.name}}. Please upload a CSV file.")
    st.stop()

raw= CSV_path.read_bytes()

try:
    data = load_data(raw)
except ValueError as err:
    st.error(str(err))            
    st.stop()


st.sidebar.header("Filter")

states=st.sidebar.multiselect(
    "State",sorted(data["State"].unique()),placeholder="All States"
)
zones=st.sidebar.multiselect(
    "Zone",sorted(data["Zone"].unique()),placeholder="All Zones"
)
statuses=st.sidebar.multiselect(
    "Attendance",sorted(data[Status].unique()),placeholder="All"
)
search=st.sidebar.text_input(
    "search name, church,school or email",placeholder="e.g Lautech"
)

data1=data
if states:
    data1=data1[data1["State"].isin(states)]
if zones:
    data1=data1[data1["Zone"].isin(zones)]    
if statuses:
    data1=data1[data1[Status].isin(statuses)]
if search.strip():
    q=search.strip()
    mask=pd.Series(False,index=data1.index)
    for col in ["Full Name","Church","School","Email"]:
        mask |=data1[col].str.contains(q,case=False,regex=False)
    data1=data1[mask]

st.sidebar.caption(f"Showing {len(data1):,} of {len(data):,} Records")
if data1.empty:
    st.warning("No Records match the current Filter.")
    st.stop()

     


total=len(data1)
present=int(data1["Present"].sum())

k1,k2,k3,k4,k5=st.columns(5)
k1.metric("Registered",f"{total:,}")
k2.metric("Present",f"{present:,}")
k3.metric("Not Checked In",f"{total - present:,}")
k4.metric("Attendance Rate",f"{present/total:.1%}")
k5.metric("States Represented",
          data1.loc[data1["State"] !="Unknown","State"].nunique())

tab_overview,tab_geo,tab_orgs,tab_data=st.tabs(
    ["Overview","States & Zones","School & Church","Records"]
)          


with tab_overview:
    left, right = st.columns([1, 2])

    with left:
        st.subheader("Attendance split")
        split = data1[Status].value_counts().reset_index()
        split.columns = [Status, "Count"]
        donut = (
            alt.Chart(split, height=300)
            .mark_arc(innerRadius=70)
            .encode(
                theta="Count:Q",
                color=alt.Color(f"{Status}:N", scale=S_Color, title=None,
                                legend=alt.Legend(orient="bottom")),   
                tooltip=[Status, "Count"],
            )
        )
        st.altair_chart(donut, width="stretch")

    with right:
        st.subheader("Attendance rate by Zone")
        rate = (
            data1.groupby("Zone")["Present"].agg(["mean", "sum", "count"]).reset_index() 
        )
        rate.columns = ["Zone", "Rate", "Present", "Registered"]      
        rate_chart = (
            alt.Chart(rate, height=300)
            .mark_bar(color="#2e7d32")
            .encode(
                x=alt.X("Zone:N", sort=Zone_order(rate["Zone"]), title="Zone",
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Rate:Q", axis=alt.Axis(format="%"), title="Attendance rate"),
                tooltip=["Zone", alt.Tooltip("Rate:Q", format=".1%"), "Present", "Registered"],
            )
        )
        st.altair_chart(rate_chart, width="stretch")

    st.subheader("Registration by State")                          
    st.altair_chart(stacked_bar(data1, "State"), width="stretch")


with tab_geo:
    st.subheader("Registration by Zone")
    z_order = Zone_order(data1["Zone"].unique())                   
    st.altair_chart(stacked_bar(data1, "Zone", order=z_order), width="stretch")

    st.subheader("Zone x State heatmap")
    grid = data1.groupby(["State", "Zone"]).size().reset_index(name="Count")
    s_order = data1["State"].value_counts().index.to_list()
    base = alt.Chart(grid, height=max(260, 28 * len(s_order))).encode(
        x=alt.X("Zone:N", sort=z_order, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("State:N", sort=s_order, title=None),
    )
    heat = base.mark_rect().encode(
        color=alt.Color("Count:Q", scale=alt.Scale(scheme="greens"), title="People"),
        tooltip=["State", "Zone", "Count"],
    )
    labels = base.mark_text(fontSize=11).encode(
        text="Count:Q",
        color=alt.condition(alt.datum.Count > grid["Count"].max() * 0.55,
                            alt.value("white"), alt.value("black")),
    )
    st.altair_chart(heat + labels, width="stretch")


with tab_orgs:
    c1, c2 = st.columns([3, 1])                                    
    top_n = c1.slider("How many to show", 5, 40, 15)
    show_unknown = c2.checkbox("Include 'Unknown'", value=False)
    st.subheader("Top Schools")
    st.altair_chart(top_N_chart(data1, "School", top_n, show_unknown), width="stretch")
    st.subheader("Top Churches")
    st.altair_chart(top_N_chart(data1, "Church", top_n, show_unknown), width="stretch")
    st.caption("Church and school names were typed freely by registrants, so variants "
               "like 'NLGC' and 'New Life Gospel Church' are counted separately.")


with tab_data:
    hide_contact=st.checkbox("Hide phone numbers and emails",value=True)
    cols=[c for c in data1.columns if c not in ("Present","Duplicate Name")]
    if hide_contact:
        cols=[c for c in cols if c not in ("Phone","Email")]
    st.dataframe(data1[cols],width="stretch",hide_index=True)
    st.download_button("Download Filter data(CSV)",
    data1.drop(columns=["Present","Duplicate Name"]).to_csv(index=False).encode(),
    file_name="filtered registrations.csv",
    mime="text/csv",
    )
    with st.expander("Data Quality"):
        q1,q2,q3 =st.columns(3)
        q1.metric ("School Unknown",f"{(data1['School']=='Unknown').mean():.0%}")
        q2.metric("Email Unknown",f"{(data1['Email']=='Unknown').mean():.0%}")
        q3.metric("Repeateded Names",int(data1["Duplicate Name"].sum()))

        dupes=data1[data1["Duplicate Name"]].sort_values("Full Name")
        if not dupes.empty:
            st.caption("Names that appers more than ones(same name, possibly different phone number):")
            dup_cols=["Full Name","Church","State","Zone",Status]
            st.dataframe(dupes[dup_cols],width="stretch",hide_index=True)
