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
import statistics
from PIL import ImageFont

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

def get_text_width(font_size, names):
    widths = {}
    for text in names:
        font = ImageFont.truetype("fonts/SourceSansPro-Regular.DZLUzqI4.ttf", font_size)
        bbox = font.getbbox(text)
        width = bbox[2] - bbox[0]
        widths[text] = width + 4
    return widths

def style_table(df, min_width_value, className, fontsize):
    width_string="90%, 30px"
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

def display_round(all_rounds_data, date, holes, pars, current_course, current_layout, names, font_size, widths):
    with st.container(border=True):
        st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>{current_course}</p>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: left; font-size: clamp(13px, 2.5vw, 17px);'>⛳️&nbsp;&nbsp;{current_layout}</p>", unsafe_allow_html=True)
        if date != "NA":
            utc_tz = pytz.timezone('UTC')
            nz_tz = pytz.timezone('Pacific/Auckland')
            utc_time = datetime.strptime(date, "%Y-%m-%d %H%M")
            utc_time = utc_tz.localize(utc_time)
            nz_time = utc_time.astimezone(nz_tz)
            formatted_date_time = "🗓️&nbsp;&nbsp;" + nz_time.strftime("%a, %-d %b %Y") + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;🕒&nbsp;&nbsp;" + nz_time.strftime("%I:%M %p").lstrip("0")
            st.markdown(f"<p style='text-align: left; font-size: clamp(13px, 2.5vw, 17px);'>{formatted_date_time}</p>", unsafe_allow_html=True)
        else:
            pass
        names = sorted(
            names, 
            key=lambda name: (-round(all_rounds_data[name][-2] - all_rounds_data[name][-1]), all_rounds_data[name][-1])
        )
        first_place_value = (
            round(all_rounds_data[names[0]][-2] - all_rounds_data[names[0]][-1]), 
            all_rounds_data[names[0]][-1]
        )
        first_place_names = [
            name for name in names 
            if (round(all_rounds_data[name][-2] - all_rounds_data[name][-1]), all_rounds_data[name][-1]) == first_place_value
        ]
        first_place_string = first_place_names[0] if len(first_place_names) == 1 else " and ".join(first_place_names) if len(first_place_names) == 2 else ", ".join(first_place_names[:-1]) + ", and " + first_place_names[-1]
        if len(names)>1:
            st.markdown(f"<p style='text-align: left; font-size: clamp(13px, 2.5vw, 17px);'>👑&nbsp;&nbsp;{first_place_string}</p>", unsafe_allow_html=True)
        cols = st.columns(len(names))
        current_max = 0
        fillers = []
        for index, name in enumerate(names):
            with cols[index]:
                player_data = all_rounds_data[name]
                current_max =  max(round(player_data[1] - player_data[2]), current_max)
                if round(player_data[1] - player_data[2]) < sum(pars):
                    if round(player_data[1] - player_data[2]) == current_max:
                        filler_ting = " (P)"
                    else:
                        filler_ting = " (PP)"
                else:
                    filler_ting = ""
                fillers += [filler_ting]
                score_display = f"{'+' if player_data[2] > 0 else ''}{'E' if player_data[2] == 0 else player_data[2]} ({player_data[1]})"
                st.markdown(f"<p style='text-align: center; font-size: clamp(13px, 2.5vw, 17px); font-weight: bold;'>{name}{filler_ting}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center; font-size: clamp(13px, 2.5vw, 17px)'>{score_display}</p>", unsafe_allow_html=True)
        if fillers != [""] * len(cols):
            htmlting = f"<div style='line-height:0.75; padding-bottom:5px'><p style='text-decoration: underline; text-align: left; font-size: clamp(12px, 2vw, 16px)'>Notes</p>"
            if " (P)" in fillers:
                htmlting += f"<p style='text-align: left; font-size: clamp(13px, 2.5vw, 17px)'>(P) - Partial round</p>"
            elif " (PP)" in fillers:
                htmlting += f"<p style='text-align: left; font-size: clamp(13px, 2.5vw, 17px)'>(PP) - Fewer holes played than others</p>"
            st.markdown(htmlting+"</div>", unsafe_allow_html=True)
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
            chunk_size = 18
            num_chunks = len(holes) // chunk_size + (1 if len(holes) % chunk_size != 0 else 0)
            string_width = max([widths[name] for name in names if name in widths])
            for i in range(num_chunks):
                start = i * chunk_size
                end = min((i + 1) * chunk_size, len(holes))
                current_holes = holes[start:end]
                current_pars = pars[start:end]
                table = [["Hole"] + current_holes, ["Par"] + current_pars]
                for player in names:
                    table.append([player] + all_rounds_data[player][0][start:end])
                df = pd.DataFrame(table)
                html_string += style_table(df, f"calc(min({638-string_width}px/{max(min(len(holes), chunk_size),1)},638px/{max(min(len(holes), chunk_size)+1,1)}))", "laptop-table",font_size)
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
                html_string += style_table(df, f"calc(min((11.111vw - {(104+string_width)/9}px),(10vw - 10.4px)))", "mobile-table",font_size)
                if i+1 < num_chunks:
                    html_string += '<div class="mobile-table"><hr style="margin-top:1em; margin-bottom:1em"></div>'
            st.markdown(html_string+"</div>",unsafe_allow_html=True)

def best_per_hole(rounds, dates, names):
    pars = [int(x) for x in rounds[dates[0]][0][8:] if str(x) != 'nan']
    length = len(pars)
    all_data = {}
    for name in names:
        all_data[name] = None
        tries = []
        for date in dates:
            if name in [row[0] for row in rounds[date] if len(row) > 0]:
                tries += [individuals_round(date, rounds, name, length)[0]]
        bests = []
        par_score = 0
        for i, par in enumerate(pars):
            hole_scores = []
            for roundr in tries:
                if roundr[i] != "-":
                    hole_scores += [roundr[i]]
            if len(hole_scores) == 0:
                bests += ["-"]
            else:
                bests += [min(hole_scores)]
                par_score += min(hole_scores) - par
        total = sum(item for item in bests if isinstance(item, (int, float)))
        all_data[name] = [bests, total, par_score]
    return all_data

def get_average(rounds, dates, names):
    pars = [int(x) for x in rounds[dates[0]][0][8:] if str(x) != 'nan']
    length = len(pars)
    all_data = {}
    for name in names:
        all_data[name] = None
        tries = []
        for date in dates:
            if name in [row[0] for row in rounds[date] if len(row) > 0]:
                tries += [individuals_round(date, rounds, name, length)[0]]
        avs = []
        avsf = []
        par_score = 0
        for i, par in enumerate(pars):
            hole_scores = []
            for roundr in tries:
                if roundr[i] != "-":
                    hole_scores += [roundr[i]]
            if len(hole_scores) == 0:
                avs += ["-"]
                avsf += ["-"]
            else:
                avs += [statistics.mean(hole_scores)]
                avsf += [round(float(statistics.mean(hole_scores)),1)]
                par_score += statistics.mean(hole_scores) - par
        if avs.count("-") == length:
            par_score = "-"
            total = "-"
        else:
            total = sum(item for item in avs if isinstance(item, (int, float)))
            if round(float(total),1).is_integer():
                total = int(round(float(total),1))
            else:
                total = round(float(total),1)
            if round(float(par_score),1).is_integer():
                par_score = int(round(float(par_score),1))
            else:
                par_score = round(float(par_score),1)            
        all_data[name] = [avsf, total,par_score]
                
    return all_data

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
            if name in [row[0] for row in rounds[date] if len(row) > 0]:
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

def winner_string(name, tally, plays, percentage):
    pe = format(percentage[name], "g")
    t = format(tally[name], "g")
    pl = int(plays[name])
    return f"{pe}% ({t}/{pl})"

def winner_tally (dates, rounds, names):
    tally = {}
    plays = {}
    percentage = {}
    for name in names:
        tally[name] = 0
        plays[name] = 0
        percentage[name]=0

    for date in dates:
        players = []
        for tries in rounds[date]:
            players += [tries[0]]
        if set(names).issubset(players):
            scores = []
            for go in rounds[date]:
                if go[0] in names:
                    scores += [go[5]]
                    plays[go[0]] = plays[go[0]] + 1
            min_score = min(scores)
            occs = scores.count(min_score)
            for name in names:
                for go in rounds[date]:
                    if go[0]==name and go[5]==min_score:
                        tally[name] = tally[name] + 1/occs
    for name in names:
        if plays[name] != 0:
            percentage[name] = round((tally[name]/plays[name])*100,2)
    sorted_names = sorted(
        percentage.keys(),
        key=lambda name: (plays[name] == 0, -percentage[name], list(percentage.keys()).index(name))
    )
    highest_win = percentage[sorted_names[0]]
    top_winners = [name for name in sorted_names if percentage[name] == highest_win]
    top_winners_str = " and ".join(top_winners) if len(top_winners) < 3 else ", ".join(top_winners[:-1]) + " and " + top_winners[-1]
    if sum(play > 0 for play in plays.values()) != 0:
        st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>Rounds with {', '.join(names[:-1])} and {names[-1]}</p>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: left; font-size: clamp(13px, 2.5vw, 17px);'>👑&nbsp;&nbsp;{top_winners_str}</p>", unsafe_allow_html=True)
        cols = st.columns(len(names))
        for index, name in enumerate(sorted_names):
            with cols[index]:
                st.markdown(f"<p style='text-align: center; font-size: clamp(13px, 2.5vw, 17px); font-weight: bold;'>{name}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center; font-size: clamp(13px, 2.5vw, 17px)'>{winner_string(name, tally, plays, percentage)}</p>", unsafe_allow_html=True)
    else:
        st.markdown("<p>""</p>", unsafe_allow_html=True) 
        st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>No head to head matchups</p>", unsafe_allow_html=True)

def high_scores(names, dates, rounds):  
    par_total = rounds[dates[0]][0][5]
    if len(names) > 0:
            scores = []
            for date in dates:
                for attempt in rounds[date]:
                    if attempt[0] in names:
                        scores += [[attempt[0], date, attempt[5], attempt[6]]]
            filtered_scores = []
            max_attempt = 0
            for score in scores:
                max_attempt = max(max_attempt, score[2] - score[3])
            for score in scores:
                if score[2] - score[3] == max_attempt:
                    if max_attempt < par_total:
                        score[0] = score[0] + " (P)"
                    filtered_scores += [score]
            filtered_scores.sort(key=lambda x: (-(x[2] - x[3]), x[3], -(int(x[1].replace("-", "").replace(" ", ""))), x[0]))
            if len(filtered_scores) > 10:
                num = st.slider("No. of Results", 10, len(filtered_scores))
            else:
                num = len(filtered_scores)
    st.markdown("<p></p>", unsafe_allow_html=True)
    with st.container(border=True):
        if len(names) > 0:
            for score in filtered_scores[:num]:
                st.write(f"{score[0]}, {score[1]}, {score[2]}, {score[3]}")
        else:
            st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>Select at least one player</p>", unsafe_allow_html=True)



def main():
    #with st.sidebar:
        #st.page_link("files/stats.py", label="Stats")
        #st.page_link("files/update_data.py", label="Update Data")
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
            .stMain {
                position: absolute;
                inset: 0px;
            }
            .stSidebar {
                box-shadow: transparent -2rem 0px 2rem 2rem;
            }
            div[data-testid="stSidebarCollapseButton"] {
                display: inline!important;
            }
        </style>
    """, unsafe_allow_html=True)
    data, course_layouts = fetch_data()
    Course = st.selectbox("Select a course", list(course_layouts.keys()))
    Layout = st.selectbox("Select a layout", course_layouts[Course])
    dates, rounds, names = get_all_rounds(data, course_layouts, Course, Layout)
    font_size = 14
    widths = get_text_width(font_size, names)
    if Course == "All" or Layout == "All":
        types = ["Previous Rounds", "Player Comparison"]
    elif len(names) == 1:
        types = ["Previous Rounds", "Best Round", "Best Per Hole", "Average"]
    else:
        types = ["Previous Rounds", "Player Comparison", "Best Round", "Best Per Hole", "Average", 'High Scores']
    Type = st.selectbox("Select a stat", types)
    if Course is not None and Layout in course_layouts[Course]:
        st.markdown(f"<p style='text-decoration: underline;margin-bottom: 0px; text-align: left; font-size: clamp(20px, 3.7vw, 28px); font-weight: bold;'>{Type}</p>", unsafe_allow_html=True)
        st.markdown("<p></p>", unsafe_allow_html=True)
        if Type == "Previous Rounds":
            if len(dates) > 10:
                num = st.slider("No. of Results", 10, len(dates))
            else:
                num = len(dates)
            for date in dates[:num]:
                all_rounds_data, holes, pars, current_course, current_layout, round_names = get_round(date, rounds) 
                display_round(all_rounds_data, date, holes, pars, current_course, current_layout, round_names, font_size, widths)
        elif Type == "Player Comparison":
            selected_names = st.multiselect("Select Players", names)
            st.markdown("<p></p>", unsafe_allow_html=True)
            with st.container(border=True):
                if len(selected_names)>=2:
                    winner_tally(dates, rounds, selected_names)
                else:
                    st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>Select at least two players</p>", unsafe_allow_html=True)
        elif Type == "Best Round":
            all_rounds_data, holes, pars, current_course, current_layout,round_names = get_round(dates[0], rounds)
            best_rounds = get_best(rounds, dates, names)
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout, names, font_size, widths)
        
        elif Type == "Best Per Hole":
            all_rounds_data, holes, pars, current_course, current_layout,round_names= get_round(dates[0], rounds)
            best_rounds = best_per_hole(rounds, dates, names)
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout, names, font_size, widths)
        
        elif Type == "Average":
            all_rounds_data, holes, pars, current_course, current_layout,round_names = get_round(dates[0], rounds)
            best_rounds = get_average(rounds, dates, names)
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout, names, font_size, widths)
        elif Type == "High Scores":
            selected_names = st.multiselect("Select Players", names, names)
            high_scores(selected_names, dates, rounds)
            
    
main()