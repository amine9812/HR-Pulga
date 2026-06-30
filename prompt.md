You are working on an already-built HR application. The project already exists and most features are ready. For this task, you must work ONLY on the Planning tab/module and the chatbot integration related to planning and role-based Q&A.

Do not redesign or modify unrelated tabs unless a shared backend model, API, permission helper, layout component, or routing file must be adjusted to support the Planning module correctly.

The goal is to transform the Planning tab into a professional, intelligent HR planning system inspired by modern business/management games such as Big Ambitions, where HR users can easily create, edit, assign, drag, resize, filter, and manage employee shifts in a clean visual schedule.

The Planning module must become easy to read, easy to modify, and ready for future AI-assisted planning through a Gemini-powered chatbot.

Work box by box.

==================================================
BOX 1 — Explore the current Planning module
===========================================

First, inspect the project and identify everything related to the current Planning tab/module.

Find:

* Frontend Planning pages/components.
* Backend Planning routes/controllers/views/API endpoints.
* Database models related to planning, employees, teams, departments, roles, shifts, absences, leave requests, availability, or schedules.
* Existing authentication and role/permission logic.
* Existing chatbot or AI-related code, if any.
* Existing API structure.
* Existing styling system and UI components.

Do not start coding before understanding the current structure.

After exploration, write a short internal plan explaining:

* What currently exists.
* What is missing.
* What needs to be improved.
* Which files will be modified.
* Which files must not be touched.

==================================================
BOX 2 — Planning data model and business logic
==============================================

Improve the Planning module logic so it supports a real HR planning system.

The system should support, depending on the existing project structure:

* Employee shifts.
* Start time and end time.
* Shift date.
* Breaks / pause time / coffee time.
* Department assignment.
* Team assignment if the project has teams.
* Single employee assignment.
* Bulk assignment to a full department or full team.
* Shift status, for example planned, confirmed, modified, cancelled.
* Notes or internal HR comments.
* Optional location/work area if the project already supports it.
* Leave/absence conflict detection if leave/absence exists in the project.
* Public holidays or unavailable days if the project has them.
* Audit-friendly timestamps such as created_at and updated_at.

Add or improve validations:

* A shift cannot be created in the past unless the app explicitly allows historical records.
* Start time must be before end time.
* End time must be after start time.
* Break time must be inside the shift.
* Break duration cannot be longer than the shift.
* The same employee cannot receive overlapping shifts.
* An employee on leave/absence cannot be assigned a shift.
* A department/team bulk assignment must not create invalid duplicate shifts.
* Required fields must be validated in frontend and backend.
* Invalid values must show clear error messages.
* Time/date formatting must be consistent across the app.
* Number values such as duration, hours, or break time must never become negative, NaN, empty, or logically impossible.

If schema changes are needed, create proper migrations or update the existing schema cleanly according to the project stack.

Do not break existing data.

==================================================
BOX 3 — Professional Planning UI layout
=======================================

Redesign only the Planning tab UI to make it professional, clean, and easy to use.

The Planning tab should include:

1. Header section

* Title: Planning
* Short description explaining that HR can manage employee schedules.
* Main action button: Add Shift / Create Planning
* Optional action buttons: Export, Reset Filters, Today, Previous Week, Next Week.

2. Filters section

Add professional filters such as:

* Date range.
* Week selector.
* Department filter.
* Team filter if teams exist.
* Employee filter.
* Role filter if useful.
* Shift status filter.
* Search by employee name.
* Reset filters button.

Filters must be easy to understand and must work correctly.

3. Calendar/planning grid

Create a visual planning grid that is easy to read.

Preferred behavior:

* Rows = employees, teams, or departments depending on selected view.
* Columns = days/time blocks.
* Shift blocks appear visually inside the grid.
* Each shift block should show employee name, time range, department/team, and status.
* Shift colors or badges can represent status or department.
* Empty states should be clean and professional.
* Loading states should be clear.

Support multiple views if reasonable:

* Day view.
* Week view.
* Department view.
* Employee view.

Do not overcomplicate if the current project is simple, but make it look like a real HR/business planning system.

4. Side panel or modal

When creating/editing a shift, use a professional modal or side panel with:

* Employee selector.
* Department/team selector.
* Date.
* Start time.
* End time.
* Break/pause time.
* Status.
* Notes.
* Save button.
* Cancel button.
* Validation messages.

5. Readability

The planning must be easy for HR users to understand at a glance.

Improve:

* Spacing.
* Alignment.
* Labels.
* Tables/grid readability.
* Buttons.
* Empty states.
* Error states.
* Success messages.
* Responsive behavior.

Keep the project’s existing visual identity. Do not create a completely different design language.

==================================================
BOX 4 — Drag-and-drop planning behavior
=======================================

Add or improve drag-and-drop behavior in the Planning tab if compatible with the existing stack.

The HR user should be able to:

* Drag a shift to another time/day.
* Drag a shift to another employee if allowed.
* Resize a shift to change start/end time if technically reasonable.
* Click a shift to edit it.
* Duplicate/copy a shift.
* Delete or cancel a shift.
* Move shifts while respecting validation rules.

Important rules:

* Dragging must not allow invalid dates.
* Dragging must not create overlapping shifts.
* Dragging must not assign a shift to an unavailable employee.
* If a drag action is invalid, revert the shift visually and show a clear error.
* After a successful drag, update the backend/database.
* Do not only change the frontend state; the persisted data must be updated too.
* Use an existing drag/drop library if the project already has one.
* If adding a library is necessary, choose a stable and appropriate one for the stack.
* Do not add unnecessary heavy dependencies.

==================================================
BOX 5 — Intelligent planning features
=====================================

Add practical intelligent planning helpers, without making the system fully automatic.

The system should help HR users plan faster, but HR remains in control.

Add features where possible:

* Bulk create shifts for a department.
* Bulk create shifts for a team.
* Apply the same schedule to multiple employees.
* Copy a planning from one day/week to another.
* Add break/pause time automatically inside a shift.
* Detect conflicts before saving.
* Show warnings for overloaded employees.
* Show warnings for missing coverage if the project has coverage rules.
* Show total hours per employee.
* Show total planned hours per department/team.
* Show shift count.
* Show invalid or conflicting shifts clearly.
* Add a small summary card area above the planning grid.

Example summary cards:

* Total planned shifts.
* Employees planned this week.
* Total planned hours.
* Conflicts detected.
* Employees without planning.

All calculations must be based on real project data.

==================================================
BOX 6 — Planning API readiness
==============================

Make the Planning module API-ready so that the chatbot and future integrations can interact with it cleanly.

Create or improve backend APIs/services for:

* List planning entries.
* Get one planning entry.
* Create a shift.
* Update a shift.
* Delete/cancel a shift.
* Move a shift.
* Resize/change shift duration.
* Bulk assign shifts to department/team/employees.
* Copy planning from one period to another.
* Check planning conflicts.
* Get planning summary/statistics.
* Get employees available for a date/time range.

API behavior must be clean:

* Return consistent JSON responses.
* Return clear validation errors.
* Enforce role permissions.
* Never expose data to users who should not access it.
* Keep API names and routes consistent with the existing project style.
* Reuse existing authentication and authorization helpers.
* Do not duplicate business logic between frontend and backend. Put critical logic in backend services.

==================================================
BOX 7 — Gemini chatbot integration
==================================

Add or prepare a chatbot system using Gemini API.

The project has a Gemini API key. Use environment variables and never hardcode the key.

Expected environment variable example:

GEMINI_API_KEY=your_key_here

The chatbot must support two main modes:

1. RAG-based Q&A mode

The chatbot answers questions about the app and the user’s accessible data.

Rules:

* The chatbot must answer only based on the project data, project documentation, app features, database information, and user-accessible records.
* It must not hallucinate features that do not exist.
* It must respect user roles.
* HR users can ask about HR-accessible features and planning data.
* Regular employees can only ask about their own information.
* An employee must not be able to ask about another employee’s private information.
* If the user asks for data they do not have access to, the chatbot must refuse politely.
* If the information is not available in the app, the chatbot must say that it does not have enough information.

Implement or prepare a simple RAG pipeline depending on the project stack:

* Collect relevant internal context from project data.
* Retrieve only data allowed for the current user role.
* Send only authorized context to Gemini.
* Return a clear answer.
* Keep responses concise and useful.

2. Planning action mode for HR users only

HR users should be able to type planning commands, and the chatbot should help modify the Planning module.

Examples of commands:

* “Assign next Monday 9:00 to 17:00 to all employees in the Sales department.”
* “Give Ahmed a shift tomorrow from 8:00 to 16:00 with a 30-minute break.”
* “Move Sara’s Tuesday shift to Wednesday at the same time.”
* “Cancel all planning entries for the IT department next Friday.”
* “Copy this week’s planning to next week for the Support team.”
* “Show me conflicts in this week’s planning.”
* “Who has no planning this week?”
* “Add a coffee break from 10:30 to 10:45 for the morning team.”

The chatbot must parse the HR instruction and map it to planning actions.

Implementation requirements:

* Create a clear planning action layer/tool layer.
* Do not let Gemini directly modify the database.
* Gemini should interpret the command and return a structured action.
* The backend must validate the action before applying it.
* The backend must enforce permissions before applying it.
* Invalid actions must be rejected with clear explanations.
* After applying a valid action, return a clear success message and refresh/update the Planning UI.
* If the request is ambiguous, ask the HR user for clarification.
* If there are conflicts, show the conflicts and do not silently create broken planning entries.

Even though advanced security will be improved later, include basic role checks now:

* Only HR/admin/responsible roles can modify planning through the chatbot.
* Employees cannot modify planning.
* Employees cannot access other employees’ private planning information unless the existing app already allows it.
* All chatbot planning actions must go through backend validation.

==================================================
BOX 8 — Chatbot UI
==================

Add a clean chatbot interface that fits the current app.

The chatbot should be accessible in a way that makes sense for the app, preferably:

* A small floating assistant button, or
* A chatbot panel inside the Planning tab, or
* A dedicated assistant section if the project already has one.

For the Planning tab, the chatbot should help HR users interact with planning.

UI requirements:

* Message input.
* Send button.
* Loading state.
* Error state.
* Clear assistant messages.
* Clear user messages.
* Optional suggested commands.
* Chat history during the session.
* Clear indication of what the chatbot can do.
* For non-HR employees, hide or disable planning modification commands.

Do not make the chatbot visually overwhelming.

==================================================
BOX 9 — Tests and validation
============================

Add or update tests where possible.

Test the Planning module for:

* Creating a valid shift.
* Rejecting a past-date shift.
* Rejecting start time after end time.
* Rejecting overlapping shifts.
* Rejecting shift assignment during employee leave/absence if the project supports leave.
* Bulk department assignment.
* Bulk team assignment if teams exist.
* Drag/move shift update.
* Planning filters.
* Planning summary calculations.
* Role restrictions.
* Employee privacy restrictions.
* Chatbot Q&A access control.
* Chatbot planning action access control.
* Gemini API failure handling.
* Missing Gemini API key handling.

Run available commands:

* Install/build command if needed.
* Type check if applicable.
* Lint if applicable.
* Backend tests if applicable.
* Frontend tests if applicable.
* Build command.
* Migration check if applicable.

Do not leave the app broken.

==================================================
BOX 10 — Final report
=====================

At the end, provide a clear final report with:

1. What was changed in the Planning tab.

2. What was added:

   * Planning grid.
   * Filters.
   * Drag-and-drop.
   * Bulk planning.
   * Break/pause system.
   * Conflict detection.
   * Summary cards.
   * API endpoints/services.
   * Gemini chatbot.
   * RAG system.
   * Planning action system.

3. Files modified.

4. New environment variables required.

5. Commands run and results.

6. Tests added or updated.

7. Remaining limitations or recommendations.

==================================================
IMPORTANT CONSTRAINTS
=====================

* Focus only on the Planning tab/module and chatbot integration.
* Do not rewrite the whole project.
* Do not break existing tabs.
* Do not change unrelated features.
* Do not hardcode the Gemini API key.
* Do not let Gemini directly write to the database.
* Do not ignore role permissions.
* Do not expose private employee data.
* Do not create fake planning data unless the project already has seed/demo data.
* Do not make only UI changes; the planning must actually work.
* Do not make only backend changes; the planning must be easy to use visually.
* Keep code clean, maintainable, and consistent with the existing project architecture.
* Use the existing project conventions whenever possible.

Start now by exploring the project, identifying the current Planning tab/module, then implement the work box by box.
