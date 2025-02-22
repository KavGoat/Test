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

st.markdown("""
    <style>
           /* Remove blank space at top and bottom */
           .stMainBlockContainer {
               padding-top: 3rem;
               padding-left: 1rem;
               padding-right: 1rem;
               padding-bottom: 10rem;
            }
    </style>
    """, unsafe_allow_html=True)

custom_css = """
    <style>
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
    </style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

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

def winner (rounds):
    names = ["Kav", "Nethidu", "Mahith"]
    scores = []
    for name in names:
        if rounds[name][-1] != "-":  # Check if the last value is not "-"
            scores += [rounds[name][-1]]
    players = len(scores)
    best_score = min(scores)
    winners = []
    for name in names:
        if rounds[name][-1] != "-" and rounds[name][-1] == best_score:
            winners += [name]
    if len(winners) == 1:
        return [players, winners[0]]
    elif len(winners) == 2:
        return [players, f"{winners[0]} and {winners[1]}"]
    else:
        return [players, ", ".join(winners[:-1]) + " and " + winners[-1]]
    
def winner_order(name, all_rounds_data):
    last_value = all_rounds_data[name][-1]
    return (float('inf') if last_value == "-" else last_value)

def get_all_rounds(data, course_layouts, Course, Layout):
    dates = []
    for rounds in data:
        if Course == "All":
            date = rounds[3]
        elif Layout == "All":
            if rounds[1] == Course:
                date = rounds[3]
        elif rounds[1] == Course and rounds[2] == Layout:
            date = rounds[3]
        try:
            if date not in dates:
                dates += [date]
        except:
            pass
    dates.sort(reverse=True)
    rounds = {}
    
    for date in dates:
        ting = []
        for attempt in data:
            if attempt[3] == date:
                ting += [attempt]
        rounds[date] = ting
    return dates, rounds

def individuals_round(date, rounds, name, length):
    individuals_data = ["-"] * length
    for individuals in rounds[date]:
        if individuals[0]==name:
            individuals_data = ["-" if x == 0 else int(x) for x in individuals[8:8+length]]
            return [individuals_data, int(individuals[5]), int(individuals[6])]
        else:
            pass
    return [individuals_data, "-", "-"]

def get_round(date, rounds):
    names = ["Kav", "Nethidu", "Mahith"]
    par_score = int(rounds[date][0][5])
    pars = [int(x) for x in rounds[date][0][8:] if str(x) != 'nan']
    length = len(pars)
    holes = list(range(1, length + 1))
    all_rounds_data = {}
    current_course=rounds[date][0][1]
    current_layout=rounds[date][0][2]
    for name in names:
        all_rounds_data[name]=individuals_round(date, rounds, name, length)
    return all_rounds_data, holes, pars, current_course, current_layout

def best_per_hole(rounds, dates):
    names = ["Kav", "Nethidu", "Mahith"]
    pars = [int(x) for x in rounds[dates[0]][0][8:] if str(x) != 'nan']
    length = len(pars)
    all_data = {}
    for name in names:
        all_data[name] = None
        tries = []
        for date in dates:
            tries += [individuals_round(date, rounds, name, length)[0]]
        bests = []
        par_score = 0
        for i, par in enumerate(pars):
            hole_scores = []
            for round in tries:
                if round[i] != "-":
                    hole_scores += [round[i]]
            if len(hole_scores) == 0:
                bests += ["-"]
            else:
                bests += [min(hole_scores)]
                par_score += min(hole_scores) - par
        if bests.count("-") == length:
            par_score = "-"
            total = "-"
        else:
            total = sum(item for item in bests if isinstance(item, (int, float)))
        all_data[name] = [bests, total, par_score]
                
    return all_data

def get_average(rounds, dates):
    names = ["Kav", "Nethidu", "Mahith"]
    pars = [int(x) for x in rounds[dates[0]][0][8:] if str(x) != 'nan']
    length = len(pars)
    all_data = {}
    for name in names:
        all_data[name] = None
        tries = []
        for date in dates:
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

def get_best(rounds, dates):
    names = ["Kav", "Nethidu", "Mahith"]
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

def style_table(df, min_width_value, className, fontsize):
    if fontsize == 14:
        width_string="90%, 30px"
    else:
        width_string="95%, 31.667px"
    pars = df.iloc[1].values.tolist()
    prelim_columns = df.iloc[:2].values.tolist()
    df.columns = [[str(sublist[0])] + [str(int(x)) for x in sublist[1:]] for sublist in prelim_columns]
    df = df[2:].reset_index(drop=True)

    # Get the par value from the second row of the header (adjusted column-wise)
    # Assuming par is in the second row of the second column

    # Wrap each cell content in a <div> for all cells in the table body (excluding the first column)
    def wrap_in_div(val, row_idx, col_idx, pars):
        par = pars[col_idx]
        # If val is "-", set background-color to transparent and border-radius to 0
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

        # Apply div wrapping for body cells (excluding first column and first two rows)
        if col_idx > 0:
            # Determine background color based on val compared to par
            if val == 1:
                background_color = "#44AD86"
                border_radius = "20%"
                #return f'''<div style="display: flex; justify-content: center; align-items: center;  overflow: hidden; justify-self: center;
                #            width: calc(min({width_string}) * 0.8); aspect-ratio: 1/1; background-color: {background_color}; 
                #            border-radius: {border_radius}; transform: rotate(45deg); text-align:center;">
                #                <span style="display: block; transform: rotate(-45deg);">{val}</span>
                #          </div>'''
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
                background_color = "#BF896C"  # Light orange
            elif val > par + 1 and val <= par + 2:
                background_color = "#C16E46"  # Orange
            elif val > par + 2:
                background_color = "#AA5129"  # Dark orange
            elif val < par and val >= par - 1:
                background_color = "#28406A"  # Light blue
            elif val < par - 1 and val >= par -2:
                background_color = "#4F6A97"  # Blue
            elif val < par - 2:
                background_color = "#7798CB"  # Dark blue
            else:
                background_color = "transparent"  # Default

            # Determine border-radius based on whether it's bogey or under par
            border_radius = "20%" if val > par else "100%"

            #return f'<div style="display: flex; justify-content: center; align-items: center; ' \
            #       f'width: min({width_string}); aspect-ratio: 1 / 1; justify-self: center;overflow: hidden;' \
            #       f'background-color: {background_color}; border-radius: {border_radius};text-align:center; line-height:1;">{val}</div>'
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

    # Apply wrap_in_div to each cell, passing row and column indices
    for row_idx, row in df.iterrows():
        for col_idx, val in enumerate(row):
            df.at[row_idx, df.columns[col_idx]] = wrap_in_div(val, row_idx, col_idx,pars)   

    # Styling the DataFrame as before
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


def display_round(all_rounds_data, date, holes, pars, current_course, current_layout):
    st.markdown("""
        <style>
            .stHorizontalBlock {
                display: flex;
                flex-wrap: nowrap;
            }
            .stHorizontalBlock .stColumn {
                width: calc(33.3333333% - 1rem); /* Adjust width */
                min-width: unset;               /* Unset min-width */
            }
        </style>
    """, unsafe_allow_html=True)
    with st.container(border=True):
        # Display Course and Layout (Left-Aligned)
        st.markdown(f"<p style='text-align: left; font-size: clamp(18px, 3.5vw, 26px); font-weight: bold;'>{current_course}</p>", unsafe_allow_html=True)
        st.markdown(f"<p style='text-align: left; font-size: clamp(13px, 2vw, 16px);'>⛳️&nbsp;&nbsp;{current_layout}</p>", unsafe_allow_html=True)
        

        # Given UTC time
        if date == "NA":
            pass
        else:
            utc_tz = pytz.timezone('UTC')
            nz_tz = pytz.timezone('Pacific/Auckland')
            utc_time = datetime.strptime(date, "%Y-%m-%d %H%M")
            utc_time = utc_tz.localize(utc_time)
            nz_time = utc_time.astimezone(nz_tz)
            formatted_date_time = "🗓️&nbsp;&nbsp;" + nz_time.strftime("%a, %-d %b %Y") + "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;🕒&nbsp;&nbsp;" + nz_time.strftime("%I:%M %p").lstrip("0")
            st.markdown(f"<p style='text-align: left; font-size: clamp(13px, 2vw, 16px);'>{formatted_date_time}</p>", unsafe_allow_html=True)
        winner_data = winner(all_rounds_data)
        if winner_data[0]>1:
            st.markdown(f"<p style='text-align: left; font-size: clamp(13px, 2vw, 16px);'>👑&nbsp;&nbsp;{winner_data[1]}</p>", unsafe_allow_html=True)
      # Create Columns
        col1, col2, col3 = st.columns(3)
        cols = [col1, col2, col3]
        names = ["Kav", "Nethidu", "Mahith"]
        names = sorted(names, key=lambda name: winner_order(name, all_rounds_data))

        # Display Player Data (Centered)
        for index, name in enumerate(names):
            with cols[index]:
                player_data = all_rounds_data.get(name, [0, 0, 0])  # Default values if missing
                score_display = f"{'+' if isinstance(player_data[2], (int, float)) and player_data[2] > 0 else ''}{'E' if player_data[2] == 0 else player_data[2]} ({player_data[1]})"
                st.markdown(f"<p style='text-align: center; font-size: clamp(13px, 2.5vw, 18px); font-weight: bold;'>{name}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='text-align: center; font-size: clamp(13px, 2vw, 16px)'>{score_display}</p>", unsafe_allow_html=True)

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
            if len(holes) > 21:
                fontsize=13
            else:
                fontsize=14
            html_string += style_table(df, f"calc(min(587px/{max(len(holes),1)},638px/{max(len(holes)+1,1)}))", "laptop-table",fontsize)
            chunk_size = 9
            num_chunks = len(holes) // chunk_size + (1 if len(holes) % chunk_size != 0 else 0)
            
            # Loop through each chunk
            for i in range(num_chunks):
                start = i * chunk_size
                end = min((i + 1) * chunk_size, len(holes))  # Ensure end does not exceed the length of holes
                current_holes = holes[start:end]
                current_pars = pars[start:end]
                
                # Create the table for the current chunk
                table = [["Hole"] + current_holes, ["Par"] + current_pars]
                for player in names:
                    table.append([player] + all_rounds_data[player][0][start:end])
                
                # Convert the table to a DataFrame
                df = pd.DataFrame(table)
                
                # Add the styled table to the html string
                html_string += style_table(df, "calc(min((11.111vw - 17.222px),(10vw - 10.4px)))", "mobile-table",14)
                if i+1 < num_chunks:
                    html_string += '<div class="mobile-table"><hr style="margin-top:1em; margin-bottom:1em"></div>'
            st.markdown(html_string+"</div>",unsafe_allow_html=True)

def trend_analysis(data, course, layout):
    # Filter data for the specific course and layout
    filtered_data = [round for round in data if round[1] == course and round[2] == layout]
    
    if not filtered_data:
        return None
    
    # Organize data by player and date
    player_scores = {}
    for round in filtered_data:
        player = round[0]
        date = datetime.strptime(round[3], "%Y-%m-%d %H%M").strftime("%Y-%m-%d")
        
        # Handle invalid total_score and par_score values
        try:
            total_score = int(round[5]) if round[5] not in ["-", "", None] and not pd.isna(round[5]) else None
            par_score = int(round[6]) if round[6] not in ["-", "", None] and not pd.isna(round[6]) else None
        except (ValueError, TypeError):
            total_score = None
            par_score = None
        
        # Skip rounds with invalid scores
        if total_score is None or par_score is None:
            continue
        
        relative_score = total_score - par_score  # Relative performance
        
        # Track the best relative score for each player
        if player not in player_scores:
            player_scores[player] = {"Date": date, "Total Score": total_score, "Relative Score": relative_score}
        else:
            if relative_score < player_scores[player]["Relative Score"]:
                player_scores[player] = {"Date": date, "Total Score": total_score, "Relative Score": relative_score}

    df = pd.DataFrame(player_scores).T.reset_index().rename(columns={"index": "Player"})
    
    return df

def main():
    data, course_layouts = fetch_data()
    Course = st.selectbox("Select a course", list(course_layouts.keys()))
    Layout = st.selectbox("Select a layout", course_layouts[Course])
    
    if Course == "All" or Layout == "All":
        types = ["Previous Rounds"]
    else:
        types = ["Previous Rounds", "Best Round", "Best Per Hole", "Average", "Trend Analysis"]  # Add "Trend Analysis" option
    
    Type = st.selectbox("Select a stat", types)
    dates, rounds = get_all_rounds(data, course_layouts, Course, Layout)
    
    if Course is not None and Layout in course_layouts[Course]:
        if Type == "Previous Rounds":
            st.markdown(f"<p style='text-decoration: underline;margin-bottom: 0px; text-align: left; font-size: clamp(20px, 3.7vw, 28px); font-weight: bold;'>Previous Rounds</p>", unsafe_allow_html=True)
            for date in dates:
                all_rounds_data, holes, pars, current_course, current_layout = get_round(date, rounds) 
                display_round(all_rounds_data, date, holes, pars, current_course, current_layout)
        
        elif Type == "Best Round":
            st.markdown(f"<p style='text-decoration: underline;margin-bottom: 0px; text-align: left; font-size: clamp(20px, 3.7vw, 28px); font-weight: bold;'>Best Round</p>", unsafe_allow_html=True)
            all_rounds_data, holes, pars, current_course, current_layout = get_round(dates[0], rounds)
            best_rounds = get_best(rounds, dates)
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout)
        
        elif Type == "Best Per Hole":
            st.markdown(f"<p style='text-decoration: underline;margin-bottom: 0px; text-align: left; font-size: clamp(20px, 3.7vw, 28px); font-weight: bold;'>Best Per Hole</p>", unsafe_allow_html=True)
            all_rounds_data, holes, pars, current_course, current_layout = get_round(dates[0], rounds)
            best_rounds = best_per_hole(rounds, dates)
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout)
        
        elif Type == "Average":
            st.markdown(f"<p style='text-decoration: underline;margin-bottom: 0px; text-align: left; font-size: clamp(20px, 3.7vw, 28px); font-weight: bold;'>Average</p>", unsafe_allow_html=True)
            all_rounds_data, holes, pars, current_course, current_layout = get_round(dates[0], rounds)
            best_rounds = get_average(rounds, dates)
            display_round(best_rounds, "NA", holes, pars, current_course, current_layout)
        
        elif Type == "Trend Analysis":
            st.markdown(f"<p style='text-decoration: underline;margin-bottom: 0px; text-align: left; font-size: clamp(20px, 3.7vw, 28px); font-weight: bold;'>Trend Analysis</p>", unsafe_allow_html=True)
            trend_data = trend_analysis(data, Course, Layout)
            
            if trend_data is not None:
                st.write(f"### Best Rounds (Relative to Par) on {Course} ({Layout})")
                
                # Display the best rounds for each player
                st.write(trend_data)
                
                # Plot the best rounds
                import plotly.express as px
                fig = px.bar(trend_data, x="Player", y="Total Score", color="Player",
                              title=f"Best Rounds (Relative to Par) on {Course} ({Layout})",
                              labels={"Player": "Player", "Total Score": "Total Score"})
                st.plotly_chart(fig)
            else:
                st.write("No trend data available for the selected course and layout.")
main()
