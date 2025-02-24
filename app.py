import streamlit as st
import pandas as pd
import numpy as np
import ssl
from io import StringIO
import sys
from contextlib import redirect_stdout
import math
import os
from datetime import datetime
import pytz
from st_pages import get_nav_from_toml
import statistics
import plotly.express as px

def fetch_data():
    try:
        repo_id = "Kavindith/data"
        data = pd.read_csv("https://huggingface.co/spaces/Kavindith/data/resolve/main/data.csv", index_col=0)
        data = data.reset_index().values.tolist()
        courses = []
        for round in data:
            if round[1] not in courses:
                courses.append(round[1])
        courses.sort()
        course_layouts = {"All": "-"}
        for course in courses:
            layouts = []
            for round in data:
                if round[1] == course and round[2] not in layouts:
                    layouts.append(round[2])
            layouts.sort()
            if len(layouts) > 1:
                layouts = ["All"] + layouts
            course_layouts[course] = layouts
        return data, course_layouts
    except:
        pass

def get_all_rounds(data, course_layouts, Course, Layout):
    dates = []
    names = []
    for rounds in data:
        if Course == "All":
            date = rounds[3]
            if rounds[0] != "Par" and rounds[0] not in names:
                names += [rounds[0]]
        elif Layout == "All":
            if rounds[1] == Course:
                date = rounds[3]
                if rounds[0] != "Par" and rounds[0] not in names:
                    names += [rounds[0]]
        elif rounds[1] == Course and rounds[2] == Layout:
            date = rounds[3]
            if rounds[0] != "Par" and rounds[0] not in names:
                names += [rounds[0]]
        try:
            if date not in dates:
                dates += [date]
        except:
            pass
    names.sort()
    dates.sort(reverse=True)
    rounds = {}
    for date in dates:
        ting = []
        for attempt in data:
            if attempt[3] == date:
                ting += [attempt]
        rounds[date] = ting
    return dates, rounds, names

def individuals_round(date, rounds, name, length):
    for individuals in rounds[date]:
        if individuals[0]==name:
            individuals_data = ["-" if x == 0 else int(x) for x in individuals[8:8+length]]
            return [individuals_data, int(individuals[5]), int(individuals[6])]
        else:
            pass

def get_round(date, rounds):
    par_score = int(rounds[date][0][5])
    pars = [int(x) for x in rounds[date][0][8:] if str(x) != 'nan']
    length = len(pars)
    holes = list(range(1, length + 1))
    all_rounds_data = {}
    current_course=rounds[date][0][1]
    current_layout=rounds[date][0][2]
    names = []
    for go in rounds[date]:
        if go[0] != "Par":
            names += [go[0]]
    names.sort()
    for name in names:
        all_rounds_data[name]=individuals_round(date, rounds, name, length)
    return all_rounds_data, holes, pars, current_course, current_layout, names

def winner (rounds, names):
    scores = []
    for name in names:
        scores += [rounds[name][-1]]
    players = len(scores)
    best_score = min(scores)
    winners = []
    for name in names:
        if rounds[name][-1] == best_score:
            winners += [name]
    if len(winners) == 1:
        return [players, winners[0]]
    elif len(winners) == 2:
        return [players, f"{winners[0]} and {winners[1]}"]
    else:
        return [players, ", ".join(winners[:-1]) + " and " + winners[-1]]

def display_round(all_rounds_data, date, holes, pars, current_course, current_layout, names):
    with st.container(border=True):
        st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>{current_course}</p>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: left; font-size: clamp(12px, 2vw, 16px);'>⛳️&nbsp;&nbsp;{current_layout}</p>", unsafe_allow_html=True)
        if date != "NA":
            utc_tz = pytz.timezone('UTC')
            nz_tz = pytz.timezone('Pacific/Auckland')
            utc_time = datetime.strptime(date, "%Y-%m-%d %H%M")
            utc_time = utc_tz.localize(utc_time)
            nz_time = utc_time.astimezone(nz_tz)
            formatted_date_time = "🗓️&nbsp;&nbsp;" + nz_time.strftime("%a, %-d %b %Y") + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;🕒&nbsp;&nbsp;" + nz_time.strftime("%I:%M %p").lstrip("0")
            st.markdown(f"<p style='text-align: left; font-size: clamp(12px, 2vw, 16px);'>{formatted_date_time}</p>", unsafe_allow_html=True)
        else:
            pass
        winner_data = winner(all_rounds_data, names)
        if winner_data[0]>1:
            st.markdown(f"<p style='text-align: left; font-size: clamp(12px, 2vw, 16px);'>👑&nbsp;&nbsp;{winner_data[1]}</p>", unsafe_allow_html=True)
        cols = st.columns(len(names))
        names = sorted(names, key=lambda name: (all_rounds_data[name][-1]))
        for index, name in enumerate(names):
            with cols[index]:
                player_data = all_rounds_data[name]
                score_display = f"{'+' if player_data[2] > 0 else ''}{'E' if player_data[2] == 0 else player_data[2]} ({player_data[1]})"
                st.markdown(f"<p style='text-align: center; font-size: clamp(13px, 2.5vw, 18px); font-weight: bold;'>{name}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center; font-size: clamp(12px, 2vw, 16px)'>{score_display}</p>", unsafe_allow_html=True)

def main():
    st.markdown("""
        <style>
            .stMainBlockContainer {
                padding-top: 3rem;
                padding-left: 1rem;
                padding-right: 1rem;
                padding-bottom: 10rem;
                }
            @media (max-width: 743px) {
                .laptop-table {
                    display: none;
                }
            }
            @media (min-width: 744px) {
                .mobile-table {
                    display: none;
                }
            }
            .stHorizontalBlock {
                display: flex;
                flex-wrap: nowrap;
            }
            .stHorizontalBlock .stColumn {
                min-width: unset;
            }
        </style>
    """, unsafe_allow_html=True)
    data, course_layouts = fetch_data()
    Course = st.selectbox("Select a course", list(course_layouts.keys()))
    Layout = st.selectbox("Select a layout", course_layouts[Course])
    if Course == "All" or Layout == "All":
        types = ["Previous Rounds", "Win Tally", "Player Comparison"]
    else:
        types = ["Previous Rounds", "Win Tally", "Player Comparison", "Best Round", "Best Per Hole", "Average"]
    Type = st.selectbox("Select a stat", types)
    dates, rounds, names = get_all_rounds(data, course_layouts, Course, Layout)
    if Course is not None and Layout in course_layouts[Course]:
        st.markdown(f"<p style='text-decoration: underline;margin-bottom: 0px; text-align: left; font-size: clamp(20px, 3.7vw, 28px); font-weight: bold;'>{Type}</p>", unsafe_allow_html=True)
        st.markdown("<p></p>", unsafe_allow_html=True)
        if Type == "Previous Rounds":
            for date in dates:
                all_rounds_data, holes, pars, current_course, current_layout, round_names = get_round(date, rounds) 
                display_round(all_rounds_data, date, holes, pars, current_course, current_layout, round_names)



main()