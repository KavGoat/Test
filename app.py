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

def get_text_width(names, font):
    widths = {}
    for text in names:
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

def display_round(all_rounds_data, date, holes, pars, current_course, current_layout, names, font_size, widths, font):
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
                st.markdown(f"<p style='text-align: center; font-size: clamp(15px, 2.5vw, 17px); font-weight: bold;'>{name}{filler_ting}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center; font-size: clamp(14px, 2.5vw, 17px)'>{score_display}</p>", unsafe_allow_html=True)
        if fillers != [""] * len(cols):
            htmlting = f"<div style='line-height:0.75; padding-bottom:5px'><p style='text-decoration: underline; text-align: left; font-size: clamp(13px, 2.5vw, 17px)'>Notes</p>"
            if " (P)" in fillers:
                htmlting += f"<p style='text-align: left; font-size: clamp(13px, 2.5vw, 17px)'>(P) - Partial round</p>"
            elif " (PP)" in fillers:
                htmlting += f"<p style='text-align: left; font-size: clamp(13px, 2.5vw, 17px)'>(PP) - Fewer holes played than others</p>"
            st.markdown(htmlting+"</div>", unsafe_allow_html=True)
        if date == "NA":
            package = st.container(border=True)
        else:
            package = st.expander("Scorecard")
        with package:
            full_table = [["Hole"] + holes, ["Par"] + pars]
            for player in names:
                full_table.append([player] + all_rounds_data[player][0])
            df = pd.DataFrame(full_table)
            html_string = "<div>"
            chunk_size = 18
            num_chunks = len(holes) // chunk_size + (1 if len(holes) % chunk_size != 0 else 0)
            string_width = max([widths[name] for name in names if name in widths])
            if date != "NA":
                html_string += '<div class="laptop-table"><hr style="margin-top:0; margin-bottom:1em"></div>'
                html_string += '<div class="mobile-table"><hr style="margin-top:0; margin-bottom:1em"></div>'
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
        if date != "NA":
            colours = {
                    "holes": "#44AD86",
                    "-3": "#7798CB",
                    "-2": "#4F6A97",
                    "-1": "#28406A",
                    "0": "transparent",
                    "1": "#BF896C",
                    "2": "#C16E46",
                    "3": "#AA5129"
                }
            with st.expander("Player Overview"):
                css = ""
                for i, name in enumerate(names):
                    valid_scores = {}
                    for index, throws in enumerate(all_rounds_data[name][0]):
                        if throws != "-":
                            if throws == 1:
                                if "holes" not in valid_scores:
                                    valid_scores["holes"] = 1
                                else:
                                    valid_scores["holes"] += 1
                            elif throws - pars[index] == 0:
                                if "0" not in valid_scores:
                                    valid_scores["0"] = 1
                                else:
                                    valid_scores["0"] += 1
                            elif throws - pars[index] == 1:
                                if "1" not in valid_scores:
                                    valid_scores["1"] = 1
                                else:
                                    valid_scores["1"] += 1
                            elif throws - pars[index]==2:
                                if "2" not in valid_scores:
                                    valid_scores["2"] = 1
                                else:
                                    valid_scores["2"] += 1
                            elif throws - pars[index]==-1:
                                if "-1" not in valid_scores:
                                    valid_scores["-1"] = 1
                                else:
                                    valid_scores["-1"] += 1
                            elif throws - pars[index]==-2:
                                if "-2" not in valid_scores:
                                    valid_scores["-2"] = 1
                                else:
                                    valid_scores["-2"] += 1
                            elif throws - pars[index] >= 3:
                                if "3" not in valid_scores:
                                    valid_scores["3"] = 1
                                else:
                                    valid_scores["3"] += 1
                            elif throws - pars[index]:
                                if "-3" not in valid_scores <= -3:
                                    valid_scores["-3"] = 1
                                else:
                                    valid_scores["-3"] += 1
                    played = 0
                    for type in valid_scores.keys():
                        played += valid_scores[type]
                    birdies = 0
                    ordered_types = []
                    all_types = ["holes", "-3", "-2", "-1", "0", "1", "2", "3"]
                    for type in all_types:
                        if type in valid_scores.keys():
                            ordered_types += [type]
                            if type in ["holes", "-3", "-2", "-1"]:
                                birdies += valid_scores[type]
                    st.markdown('<hr style="margin-bottom:1em; margin-top:0">',unsafe_allow_html=True)
                    cols = st.columns([0.6, 0.4])
                    with cols[0]:
                        st.markdown(f"<p style='font-size: clamp(15px, 2.5vw, 17px); font-weight: bold;'>{name}</p>", unsafe_allow_html=True)
                    with cols[1]:
                        st.markdown(f"<p style='font-size: 14px; text-align:right'>{round(birdies/played*100)}% Birdies</p>", unsafe_allow_html=True)
                    if i + 1 == len(names):
                        bar = """<div style="vertical-align:center; display: flex; border-radius:8px; border:solid rgba(250, 250, 250, 0.2); border-width:1px; overflow:hidden">"""
                    else:
                        bar = """<div style="vertical-align:center; display: flex; border-radius:8px; border:solid rgba(250, 250, 250, 0.2); border-width:1px; overflow:hidden; margin-bottom:1em">"""
                    for type in ordered_types:
                        bbox = font.getbbox(str(valid_scores[type]))
                        width = (bbox[2] - bbox[0] + 4)*played/valid_scores[type]+104
                        if width > 743:
                            bar += f"""<div style="width: {valid_scores[type]/played*100}%; text-align: center; font-size:{font_size}px; background-color:{colours[type]}"></div>"""                                                     
                        else:
                            className = f"{name}_{date.replace(' ', '').replace('-', '')}_{type}"
                            bar += f"""<div style="width: {valid_scores[type]/played*100}%; background-color:{colours[type]}"><div class="{className}" style="text-align: center; font-size:{font_size}px;">{valid_scores[type]}</div></div>"""
                            css += f"""
                                <style>
                                @media (max-width: {int(np.ceil(width))}px) {"{"}
                                    .{className} {"{"}
                                        display: none;
                                    {"}"}
                                {"}"}
                                </style>
                                """
                    bar += """</div>"""
                    st.markdown(bar,unsafe_allow_html=True)
                st.markdown(css, unsafe_allow_html=True)

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
            max_attempt = 0
            total_attempts = 0
            for go in rounds[date]:
                if go[0] in names:
                    max_attempt = max(max_attempt, go[5] - go[6])
                    total_attempts += go[5] - go[6]
            if max_attempt * len(names) == total_attempts:
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
                st.markdown(f"<p style='text-align: center; font-size: clamp(15px, 2.5vw, 17px); font-weight: bold;'>{name}</p>", unsafe_allow_html=True)
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
                        scores += [[attempt[0], date, round(attempt[5]), round(attempt[6])]]
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
            html_ting = "<div style='margin:0'>"
            for i, score in enumerate(filtered_scores[:num]):
                if i == 0:
                    margin_ting = "0.2em"
                else:
                    margin_ting = "1em"
                score_display = f"{'+' if score[3] > 0 else ''}{'E' if score[3] == 0 else score[3]} ({score[2]})"
                utc_tz = pytz.timezone('UTC')
                nz_tz = pytz.timezone('Pacific/Auckland')
                utc_time = datetime.strptime(score[1], "%Y-%m-%d %H%M")
                utc_time = utc_tz.localize(utc_time)
                nz_time = utc_time.astimezone(nz_tz)
                formatted_date_time = "🗓️&nbsp;&nbsp;" + nz_time.strftime("%a, %-d %b %Y")
                html_ting += f'<div style="display:flex; vertical-align:middle; margin-top:{margin_ting}; margin-bottom:1em">'
                html_ting += f'<p style="width:200px; vertical-align:middle; margin:0">{i+1})&nbsp;&nbsp;{score[0]}</p>'
                html_ting += f'<p style="width:75px; text-align:right; vertical-align:middle; margin:0">{score_display}</p>'
                html_ting += f"<p style='text-align:right; width:100%; vertical-align:middle;margin:0'>{formatted_date_time}</p>"
                html_ting += '</div>'
                if i+1 == len(filtered_scores[:num]):
                    pass
                else:
                    html_ting += '<hr style="margin:0">'
            html_ting += "</div>"
            st.markdown(html_ting, unsafe_allow_html=True)
        else:
            st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>Select at least one player</p>", unsafe_allow_html=True)

def breakdown(names, dates, rounds, font, font_size):
    colours = {
        "holes": "#44AD86",
        "-3": "#7798CB",
        "-2": "#4F6A97",
        "-1": "#28406A",
        "0": "transparent",
        "1": "#BF896C",
        "2": "#C16E46",
        "3": "#AA5129"
    }
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
        avs = []
        scores = []
        for i, par in enumerate(pars):
            hole_scores = []
            for roundr in tries:
                if roundr[i] != "-":
                    hole_scores += [roundr[i]]
            if len(hole_scores) == 0:
                bests += ["N/A"]
                avs += ["N/A"]
            else:
                bests += [min(hole_scores)]
                avs += [round(statistics.mean(hole_scores),1)]
            scores += [hole_scores]
        all_data[name] = [bests, avs, scores]
    for i, par in enumerate(pars):
        with st.container(border=True):
            css = ""
            st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>Hole {i+1} - Par {par}</p>", unsafe_allow_html=True)
            for x, name in enumerate(names):
                st.markdown('<div><hr style="margin-top:0; margin-bottom:1em"></div>', unsafe_allow_html=True)
                col1, col2 = st.columns([0.3, 0.7])
                with col1:
                    st.markdown(f"<p style='font-size: clamp(15px, 2.5vw, 17px); vertical-align: middle; font-weight: bold;'>{name}</p>", unsafe_allow_html=True)
                with col2:
                    birdies = 0
                    for ting in all_data[name][2][i]:
                        if ting == 1:
                            birdies += 1
                        elif ting - par < 0:
                            birdies += 1
                    played = len(all_data[name][2][i])
                    data_html = '<div style="display:flex; width:100%; align-content:right; text-align:right; justify-content:right">'
                    data_html += f"<div style='font-size: 14px; width: 60px; text-align:left; vertical-align: middle;'>Best:&nbsp;{all_data[name][0][i]}</div>"
                    data_html += f"<div style='font-size: 14px; width: 85px; text-align:left; vertical-align: middle;'>Average:&nbsp;{all_data[name][1][i]}</div>"
                    if all_data[name][0][i] == "N/A":
                        data_html += f"<div style='font-size: 14px; width: 85px; text-align:left; vertical-align: middle;'>Birdies:&nbsp;N/A</div>"
                    else:
                        data_html += f"<div style='font-size: 14px; width: 85px; text-align:left; vertical-align: middle;'>Birdies:&nbsp;{int(round(birdies/played*100))}%</div>"
                    data_html += "</div>"
                    st.markdown(data_html, unsafe_allow_html=True)
                if all_data[name][0][i] == "N/A":
                    if x + 1 == len(names):
                        bar = """<div style="vertical-align:center; text-align: center; border-radius:8px; border:solid rgba(250, 250, 250, 0.2); border-width:1px; overflow:hidden">N/A</div>"""
                    else:
                        bar = """<div style="vertical-align:center; text-align: center; border-radius:8px; border:solid rgba(250, 250, 250, 0.2); border-width:1px; overflow:hidden; margin-bottom:1em">N/A</div>"""
                else:
                    scoretings = {}
                    for ting in all_data[name][2][i]:
                        if ting == 1:
                            if "holes" in scoretings:
                                scoretings["holes"] += 1
                            else:
                                scoretings["holes"] = 1
                        elif ting - par <= -3:
                            if "-3" in scoretings:
                                scoretings["-3"] += 1
                            else:
                                scoretings["-3"] = 1
                        elif ting-par >= 3:
                            if "3" in scoretings:
                                scoretings["3"] += 1
                            else:
                                scoretings["3"] = 1
                        else:
                            if str(ting-par) in scoretings:
                                scoretings[str(ting-par)] += 1
                            else:
                                scoretings[str(ting-par)] = 1
                    all_types = ["holes", "-3", "-2", "-1", "0", "1", "2", "3"]
                    ordered_types = []
                    for type in all_types:
                        if type in scoretings.keys():
                            ordered_types += [type]
                    if x + 1 == len(names):
                        bar = """<div style="vertical-align:center; display: flex; border-radius:8px; border:solid rgba(250, 250, 250, 0.2); border-width:1px; overflow:hidden">"""
                    else:
                        bar = """<div style="vertical-align:center; display: flex; border-radius:8px; border:solid rgba(250, 250, 250, 0.2); border-width:1px; overflow:hidden; margin-bottom:1em">"""
                    for type in ordered_types:
                        bbox = font.getbbox(str(scoretings[type]))
                        width = (bbox[2] - bbox[0] + 4)*played/scoretings[type]+72
                        if width > 743:
                            bar += f"""<div style="width: {scoretings[type]/played*100}%; text-align: center; font-size:{font_size}px; background-color:{colours[type]}"></div>"""                                                     
                        else:
                            className = f"{name}_{i}_{type}"
                            bar += f"""<div style="width: {scoretings[type]/played*100}%; background-color:{colours[type]}"><div class="{className}" style="text-align: center; font-size:{font_size}px;">{scoretings[type]}</div></div>"""
                            css += f"""
                                    <style>
                                    @media (max-width: {int(np.ceil(width))}px) {"{"}
                                        .{className} {"{"}
                                            display: none;
                                        {"}"}
                                    {"}"}
                                    </style>
                                    """
                    bar += """</div>"""
                st.markdown(bar,unsafe_allow_html=True)
            st.markdown(css, unsafe_allow_html=True)

def main():
    #with st.sidebar:
    #    st.page_link("files/stats.py", label="Stats")
    #    st.page_link("files/update_data.py", label="Update Data")
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
    font = ImageFont.truetype("fonts/SourceSansPro-Regular.DZLUzqI4.ttf", font_size)
    widths = get_text_width(names, font)
    if Course == "All" or Layout == "All":
        types = ["Previous Rounds", "Player Comparison"]
    elif len(names) == 1:
        types = ["Previous Rounds", "Best Round", "Best Per Hole", "Average", "High Scores", "Hole Breakdown"]
    else:
        types = ["Previous Rounds", "Player Comparison", "Best Round", "Best Per Hole", "Average", 'High Scores', "Hole Breakdown"]
    Type = st.selectbox("Select a stat", types, None)
    if Course is not None and Layout in course_layouts[Course] and Type is not None:
        st.markdown(f"<p style='text-decoration: underline;margin-bottom: 0px; text-align: left; font-size: clamp(20px, 3.7vw, 28px); font-weight: bold;'>{Type}</p>", unsafe_allow_html=True)
        st.markdown("<p></p>", unsafe_allow_html=True)
        if Type == "Previous Rounds":
            if len(dates) > 10:
                num = st.slider("No. of Results", 10, len(dates))
            else:
                num = len(dates)
            for date in dates[:num]:
                all_rounds_data, holes, pars, current_course, current_layout, round_names = get_round(date, rounds) 
                display_round(all_rounds_data, date, holes, pars, current_course, current_layout, round_names, font_size, widths, font)
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
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout, names, font_size, widths, font)
        
        elif Type == "Best Per Hole":
            all_rounds_data, holes, pars, current_course, current_layout,round_names= get_round(dates[0], rounds)
            best_rounds = best_per_hole(rounds, dates, names)
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout, names, font_size, widths, font)
        
        elif Type == "Average":
            all_rounds_data, holes, pars, current_course, current_layout,round_names = get_round(dates[0], rounds)
            best_rounds = get_average(rounds, dates, names)
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout, names, font_size, widths, font)
        elif Type == "High Scores":
            if len(names) == 1:
                selected_names = names
            else:
                selected_names = st.multiselect("Select Players", names, names)
            high_scores(selected_names, dates, rounds)
        elif Type == "Hole Breakdown":
            if len(names) == 1:
                selected_names = names
            else:
                selected_names = st.multiselect("Select Players", names, names)
            if len(selected_names) == 0:
                st.markdown("<p></p>", unsafe_allow_html=True)
                with st.container(border=True):
                    st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>Select at least one player</p>", unsafe_allow_html=True)
            else:
                breakdown(selected_names, dates, rounds, font, font_size)

            
    
main()