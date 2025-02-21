# [Oxford/Cambridge Alumni Group Application](index.md)

## Pages Record

This record represents a publicly displayable web page.

This page is reached through the Edit button on an page row of the [Pages Page](pages.md):

![Pages page](images/pages_record.png)

The **back** link will take you back to the [Pages page](pages.md).

Similarly, the page's link is shown; it may be on an external site (specified in the **Link** field), or internal to the database (**Content** field of the pages record).

The **Content** is written in Markdown, and typically also includes HTML elements. It may embed dynamic content by including "[[function_name(parameters)]]" where the available options are:

- about_content('Board', 'Advisory') where the parameters are the keywords used in the *Committees* field for the Board or Officers, and additional Organizers, respectively generates the about page content
- history_content() generates the list of recent events
- upcoming_events() generates the calendar for the home page.

Note that if an external public website is being used, the above dynamic content can be supplied through the links:

- \<your_py4web_url\>/oxcam/about?board=Board&committee=Advisory
- \<your_py4web_url\>/oxcam/history
- \<your_py4web_url\>/oxcam/calendar.

All the other fields are self explanatory or are discussed on the [Pages Page](pages.md).

There are links to Markdown documentation and to HTML documentation, specifically discussing the inclusion and formatting around images.

When developing the page, after editing the Content, be sure to Submit your changes before returning to Edit and clicking the display link at the top of this page to display the effect.
