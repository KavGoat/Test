# CalcForge tasks still requiring work

Last audited: 2026-09-04

This is a conservative engineering review register derived from `docs/tasklist.md`. An item remains here until its complete requirement has been implemented and supported by appropriate validation evidence. Partial implementations and behavior that has not been verified remain listed.

This file is not the user-owned completion record. It does not change any checkbox in `docs/tasklist.md` or any status in `docs/tasklist.xlsx`.

## 1. Core concept

- Markup-only PDF document mode with calculation-specific UI hidden or disabled.
- Multiple open documents with tabs, split views, independent windows, and isolated document/tool state.

## 2. Calculation engine and equation entry

- Make fresh and existing calculation lines share the complete quote trigger, direct-unit, space-to-text, status-message, and re-entry behavior.
- Ensure recognized units render blue in every calculation state.
- Repair the remaining `=` entry/deletion failures and the visual gap before `=`.
- Use one stable typeset expression renderer during and outside editing.
- Prevent excessive zoom when editing an existing unit.
- Position unit completion directly below the expression being typed.
- Finish equation-only variable/unit completion, case-insensitive ranking, Tab acceptance, arrow/mouse navigation, and defined-variable suggestions.
- Add per-result decimal-place, scientific-notation, and significant-figure controls.
- Audit Greek glyph consistency, particularly phi.

## 3. Calculation lines and blocks

- Expose the block-only Self-contained default in both the Properties panel and style toolbar, backed by Preferences.
- Enforce the quote-only calculation trigger and prevent ordinary typing from activating tools.
- Implement backslash-triggered inline equations in text boxes, showing both formula and live result.
- Make Ctrl+Shift+M convert a calculation line/selection into a block in place.

## 4. Structural equation editor

- Complete an SMath Studio behavior audit using the supplied local installation.
- Preserve subscript structure through variable definitions such as `trib_width := ...`.
- Preserve caret/editability and Left/Right navigation after focus leaves and returns.
- Implement structural expression-tree selection, navigation, bracket wrapping, and selection-to-fraction transformation.

## 5. Spreadsheet behavior

- Paste Excel ranges as real tables while translating relative formulas where possible.
- Show row/column resize cursors at table borders.
- Prevent visual overlap between adjacent cells.
- Visually distinguish computed/output cells from input cells.
- Fix the Insert Table dialog's Header row checkbox state handling.

## 6. General placement and selection

- Apply the specified pointer anchors for callouts, images, snapshots, toolset items, groups, and clouds.
- Restrict Property mode to compatible single markup objects.
- Implement Shift-click polygon selection, closed by the first point or Enter.
- Add the optional canvas calculation insertion point and arrow-key movement.
- Make one Escape press clear selection and every nested edit/tool state.
- Eliminate all remaining stuck-tool paths, including callout-arrow placement.
- Complete the application-wide cursor-state audit and modifier-specific cursor affordances.

## 7. Shapes and control points

- Finish Cloud tool behavior and shortcut C.
- Finish the Arrow tool.
- Implement drag-vs-point Cloud/Cloud+ and cloud-callout placement, including Enter/right-click transition to text placement.
- Apply 0/45/90-degree Shift constraints consistently, including pen and highlighter.
- Add the structural break symbol to line/edge context menus.
- Expose rounded-corner and line-to-arc context commands with radius and dual arc handles.
- Support rectangle add/remove control points and automatic conversion to polygon when no longer rectangular.
- Keep arc/rounded previews visible and geometrically consistent throughout handle drags.
- Add midpoint snapping to polygon edges.

## 8. Text, callouts, and dimensions

- Support formatting only the selected text run inside a text box.
- Complete clean rotation/edit-state behavior for text boxes, rectangles, callouts, and similar objects.
- Restore callouts and other text/shape items to their correct unrotated edit orientation and default angle.
- Implement the in-place Custom Dimension workflow and Shift-dragged dimension-text leader.
- Rewrite live leader/hinge placement so in-progress and finished geometry share one path.
- Prevent leader lines from crossing their text boxes.
- Remove transient floating markup description labels.
- Remove every orange square placement marker from every markup path.

## 9. Snapshot and image operations

- Make G reliably capture PDF regions in normal and markup-only PDF modes and persist them through save/reopen/export.
- Add PDF/vector page and snapshot linework recoloring.
- Add image recolor, black-and-white, and selected-color transparency operations.
- Prevent pasted images with no stroke from acquiring a red outline.

## 10. Snapping and alignment

- Ensure disabling grid snapping actually disables it.
- Snap and show indicators on the first point of every drawing gesture.
- Make live preview snapping identical to committed geometry.
- Clear transient snap guides immediately on pointer departure, gesture end, tool change, or Escape.
- Snap new markups to both grids and existing items generally.

## 11. Move, duplicate, resize, and groups

- Complete Ctrl/Shift/Ctrl+Shift drag duplication and constraint behavior, including modifier changes mid-drag.
- Scale groups proportionally as single objects.
- Lock image/group aspect ratio by default and use Shift to release it.

## 12. Copy and paste

- Show a clear page insertion indicator when pasting pages.

## 13. Toolsets and defaults

- Show a styled default icon and Properties tag for Property-mode My Tools entries.
- Replace toolset text descriptions with real item previews/thumbnails.
- Move toolset Save to each item's context menu and make Property mode discoverable.
- Add Set as default to the Properties panel.
- Add Set as default to the style toolbar.

## 14. Panels and layout

- Build the Bluebeam-style unified dock with individually draggable panel icons on either side.
- Allow the Properties panel to resize to zero width and reopen.
- Complete selection-aware filtering for the style toolbar and Properties panel, including all type-specific controls.
- Add compact visual previews to line-style and hatch selectors.
- Allow at most one open panel per side while keeping left and right independent.
- Make wheel input over Properties dropdowns scroll the panel without changing values.

## 15. Canvas and viewport

- Eliminate cursor-anchor drift for every zoom path.
- Add a preference switching between standard wheel-scroll/Ctrl+wheel-zoom and direct-wheel zoom.
- Keep scrollbars fixed when page/view content rotates.

## 16. Keyboard shortcuts

- Disable global shortcuts during text/equation editing except text-formatting Ctrl+B/I/U.
- Require explicit text/equation entry before letter keys can be interpreted in an editor without activating markup tools.
- Make Ctrl+B Bookmark outside text editing and Bold only inside text editing.
- Expose repeat-placement-along-X/Y in the shortcut manager.

## 17. Pages and document structure

- Add per-page print/export inclusion with greyed excluded pages.
- Add editable page labels and Reset-to-imported-label behavior.
- Support multi-page selection for delete, reorder, copy, and duplicate.
- Insert PDFs dropped on the Pages panel at a visible, exact insertion position.
- Preserve real PDF vector/text content during Insert PDF.
- Remove the DPI question from Insert PDF.

## 18. Page setup and measuring

- Display current page scale next to the page number.
- Make polygon and ellipse cut-outs discoverable as holes owned by area/volume measurements.

## 19. Bookmarks and links

- Allow bookmarks to be renamed after creation.
- Preserve bookmark/link hyperlink behavior in exported PDFs.
- Prevent bookmark shortcuts while editing or selecting text.

## 20. Import and interoperability

- Import real Bluebeam BTX toolsets, hatch patterns, line types, groups, and embedded markup types from the supplied fixtures.
- Repair structural sketch-tool geometry/style fidelity against `btx/Structures - Sketch Tools.btx`.

## 21. Settings and spellcheck

- Repair dictionary coverage and inline correction suggestions, including valid words such as `requests`.

## 22. Menus and discoverability

- Make every capability reachable from the main menu bar.
- Move Preferences/settings under a Settings top-level menu.
- Add searchable command/tool search under Help.
- Audit every button/menu label for the one-or-two-word rule and move explanations to tooltips.

## 23. Reliability and process constraints

- Usage-limit continuation cannot currently be guaranteed by the application/session environment; preserve resumable state and report this constraint until platform support exists.
- Continue applying real event-driven UI validation to every interactive change; this is an ongoing acceptance requirement.

## 24. Miscellaneous reported defects

- Correct inconsistent equation spacing.
- Correct unit-completion popup placement in every editor/view state.
- Hide arrow control handles unless the arrow is selected.
- Prevent clipped/smeared rotation handles during movement.
- Identify and remove the nonfunctional blue tool.
- Audit Properties options and remove or clarify redundant controls such as Multiply highlighter.
- Remove path-dependent gaps in highlighter strokes.
- Add table row/column resize cursors.
- Prevent stale four-way move cursors and make Escape clear them.

## 25. New requests awaiting review

- Add rebindable alignment and font-size shortcuts for selected text, table cells, calculation lines, and block lines.
- Make every command shortcut and text/equation trigger visible and rebindable.
- Add in-canvas scaled numeric rectangle/ellipse size entry after the first click.
- Let cloud-callout cloud and text box move independently while leaders update.
- Add a control point to Arc items comparable to other arced segments.
- Snap pen/highlighter only at start/end points, never intermediate samples.
- Complete callout context behavior so cloud leaders can be attached at a user-chosen position. The direct commands are present, but interactive attachment choice is still missing.
- Complete modifier-order-independent Ctrl/Shift duplication and constraint behavior.
- Fully recompute leader hinges after arrow-tip, text-box, or cloud movement.
- Remove overlapping-stroke holes from highlighter rendering.
- Capture PDF vector linework and markups in Snapshot without page background or unrelated content.
- Centre the page number and label in the footer/navigation area.
- Add Pages-panel Ctrl+C/Ctrl+V, insertion indication, Ctrl/Shift multi-selection, and confirmed deletion.
- Add a continuous-versus-page-by-page bottom-canvas scroll control.
- Apply Ctrl+B/I/U only to selected text while editing and preserve global commands outside editors.
- Centre Pages-panel thumbnails in a grid layout.
- Add recoverable selective document/item flattening with a Preferences opt-out for irreversible output.
