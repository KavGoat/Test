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

def get_best(rounds, dates, names):
    pars = [int(x) for x in rounds[dates[0]][0][8:] if str(x) != 'nan']
    length = len(pars)
    all_data = {}
    for name in names:
        all_data[name] = None
        tries = []
        scores = []
        totals = []
        for date in dates:
            tries += [individuals_round(date, rounds, name, length)[0]]
            scores += [individuals_round(date, rounds, name, length)[2]]
            totals += [individuals_round(date, rounds, name, length)[1]]
        if totals.count("-") == len(totals):
            all_data[name] = [["-"] * length, '-', "-"]
        else:
            filtered_scores = [a for a in scores if a != "-"]
            filtered_totals = [a for a in totals if a != "-"]
            max_diff = max([x - y for x, y in zip(filtered_totals, filtered_scores)])
            valid_scores = []
            for i in range(len(filtered_scores)):
                if filtered_totals[i] - filtered_scores[i] == max_diff:
                    valid_scores += [filtered_scores[i]]
            min_score=min(valid_scores)
            for i in range(len(tries)):
                if scores[i] != "-":
                    if totals[i] - scores[i] == max_diff and scores[i]==min_score:
                        if all_data[name]==None:
                            all_data[name] = [tries[i], totals[i], scores[i]]
    return all_data

def wrap_in_div(val, row_idx, col_idx, pars, width_string):
        par = pars[col_idx]
        if val == "-":
            return (
                f'<div style="display: grid; width: 100%; height: 100%; '
                f'grid-template-rows: 1fr; grid-template-columns: 1fr; '
                f'justify-items: center; align-items: center;">'
                f'<div style="display: flex; justify-content: center; align-items: center; '
                f'width: min({width_string}); aspect-ratio: 1 / 1; overflow: hidden; '
                f'background-color: transparent; border-radius: 0; text-align: center; line-height: 1; '
                f'align-self: center;">{val}</div>'
                f'</div>'
            )
        if col_idx > 0:
            if val == 1:
                background_color = "#44AD86"
                border_radius = "20%"
                return (
                    f'''<div style="display: grid; width: 100%; height: 100%; 
                            grid-template-rows: 1fr; grid-template-columns: 1fr; 
                            justify-items: center; align-items: center;">
                            <div style="display: flex; justify-content: center; align-items: center; overflow: hidden; 
                                        width: calc(min({width_string}) * 0.8); aspect-ratio: 1/1; background-color: {background_color}; 
                                        border-radius: {border_radius}; transform: rotate(45deg); text-align: center;">
                                <span style="display: block; transform: rotate(-45deg);">1</span>
                            </div>
                        </div>'''
                )
            elif val == par:
                background_color = "transparent"
            elif val > par and val <= par + 1:
                background_color = "#BF896C"
            elif val > par + 1 and val <= par + 2:
                background_color = "#C16E46"
            elif val > par + 2:
                background_color = "#AA5129"
            elif val < par and val >= par - 1:
                background_color = "#28406A"
            elif val < par - 1 and val >= par -2:
                background_color = "#4F6A97"
            elif val < par - 2:
                background_color = "#7798CB"
            else:
                background_color = "transparent"
            border_radius = "20%" if val > par else "100%"
            if isinstance(val, float):
                if val.is_integer():
                    val = int(val)
            return (
                f'''<div style="display: grid; width: 100%; height: 100%; 
                        grid-template-rows: 1fr; grid-template-columns: 1fr; 
                        justify-items: center; align-items: center;">
                        <div style="display: flex; justify-content: center; align-items: center; 
                                    width: min({width_string}); aspect-ratio: 1 / 1; overflow: hidden;
                                    background-color: {background_color}; border-radius: {border_radius}; 
                                    text-align: center; line-height: 1;">{val}</div>
                    </div>'''
            )
        return val

def style_table(df, min_width_value, className, fontsize):
    if fontsize == 14:
        width_string="90%, 30px"
    else:
        width_string="95%, 31.667px"
    pars = df.iloc[1].values.tolist()
    prelim_columns = df.iloc[:2].values.tolist()
    df.columns = [[str(sublist[0])] + [str(int(x)) for x in sublist[1:]] for sublist in prelim_columns]
    df = df[2:].reset_index(drop=True)
    for row_idx, row in df.iterrows():
        for col_idx, val in enumerate(row):
            df.at[row_idx, df.columns[col_idx]] = wrap_in_div(val, row_idx, col_idx, pars, width_string)
    styled_df = df.style.set_table_styles([
        {"selector": "th, td", "props": [("font-size", f"{fontsize}px"), ("padding-right", "2px"), 
                                         ("padding-left", "2px"), ("border", "none"), 
                                         ("min-width", min_width_value)]},  
        {"selector": "thead tr:nth-child(1) th, thead tr:nth-child(2) th", 
         "props": [("font-size", f"{fontsize-1}px"), ("border", "none"), 
                   ("color", "rgb(135, 134, 134)"), ("font-weight", "bold")]},  
        {"selector": "thead tr th:first-child", "props": [("text-align", "right"), 
                                                          ("border", "none")]},  
        {"selector": "thead th:first-child, tbody td:first-child", 
         "props": [("text-align", "left"), ("border", "none")]},  
        {"selector": "th:not(:first-child), td:not(:first-child)", 
         "props": [("text-align", "center"), ("border", "none")]},
        {"selector": "tr", "props": [("border-color", "transparent"), 
                                     ("border", "none")]},  
        {"selector": "thead tr:last-child", "props": [("border-bottom", "3px solid transparent")]},  
    ]).hide(axis="index").to_html()
    styled_html = f'<div class="{className}">{styled_df}</div>'
    return styled_html

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
        if date == "NA":
            package = st.container(border=True)
        else:
            package = st.expander("See more")
        with package:
            full_table = [["Hole"] + holes, ["Par"] + pars]
            for player in names:
                full_table.append([player] + all_rounds_data[player][0])
            df = pd.DataFrame(full_table)
            html_string = "<div>"
            chunk_size = 27
            num_chunks = len(holes) // chunk_size + (1 if len(holes) % chunk_size != 0 else 0)
            if len(holes) > 21:
                fontsize=13
            else:
                fontsize=14
            for i in range(num_chunks):
                start = i * chunk_size
                end = min((i + 1) * chunk_size, len(holes))
                current_holes = holes[start:end]
                current_pars = pars[start:end]
                table = [["Hole"] + current_holes, ["Par"] + current_pars]
                for player in names:
                    table.append([player] + all_rounds_data[player][0][start:end])
                df = pd.DataFrame(table)
                html_string += style_table(df, f"calc(min(587px/{max(len(current_holes),1)},638px/{max(len(current_holes)+1,1)}))", "laptop-table",fontsize)
                if i+1 < num_chunks:
                    html_string += '<div class="laptop-table"><hr style="margin-top:1em; margin-bottom:1em"></div>'
            chunk_size = 9
            num_chunks = len(holes) // chunk_size + (1 if len(holes) % chunk_size != 0 else 0)
            for i in range(num_chunks):
                start = i * chunk_size
                end = min((i + 1) * chunk_size, len(holes))
                current_holes = holes[start:end]
                current_pars = pars[start:end]
                table = [["Hole"] + current_holes, ["Par"] + current_pars]
                for player in names:
                    table.append([player] + all_rounds_data[player][0][start:end])
                df = pd.DataFrame(table)
                html_string += style_table(df, "calc(min((11.111vw - 17.222px),(10vw - 10.4px)))", "mobile-table",14)
                if i+1 < num_chunks:
                    html_string += '<div class="mobile-table"><hr style="margin-top:1em; margin-bottom:1em"></div>'
            st.markdown(html_string+"</div>",unsafe_allow_html=True)

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