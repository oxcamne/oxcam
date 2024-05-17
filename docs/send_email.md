# [Oxford/Cambridge Alumni Group Database](index.md)

## Send Email Page

This screen, reached from the [member record](./member_record.md) or from a number of other contexts, is used to send an individual email or an email notice:

![send_email](images/send_email.png)

The template form at the top allows you to load a pre-prepared message, which can then be adjusted if necessary. You can save your work as a template by ticking the save box near the bottom of the form.

For an explicitly addressed message 'To:' will be a box allowing the entry of one or more email addresses separated by comma or space. If you are sending a notice to a mailing list or to any filtered list of members, it will describe the pre-selected target list.

If the message is explicitly addressed, or targetted to a single member, a 'Bcc:' box allows one or more bcc address(es) to be added. Depending on how email is set up, there may in effect be an implicit bcc to the sender, for example in OxCamNE transactional messages will appear in the sender's folder in the Society email. Mailing list messages may be sent via a service provider (Mailgun in OxCamNE's case) and will not be bcc'd.

The Sender field allows you select which address to use if you have multiple roles. Replies will be sent to this address.

The message body can use various metadata elements, such as \<letterhead>,  \<greeting> which include the Society letterhead and a personalized greeting (more or less formal depending on whether the member included a title when joining).  The metadata \<member> is replaced by the member's directory information, and in context \<reservation> will show details of a reservation.

[Markdown](https://www.markdownguide.org/basic-syntax/) can  be used to apply some formatting and to include links and graphics.

You can also include snippets or even large chunks of html using braces: `{{<html ...>}}`.

See [below](send_email.md#embedding-images-in-email) for a discussion of embedding images.

You can also select a file to be sent as an attachment, such as a PDF, spreadsheet, image or word document.

Ticking the 'save/update template' box allows the content to be saved for later reuse. With a complex message such as a notice containing graphics, I often develop the message as an email to my own member record, saving as a template to make sure it looks right before sending to the mailing list. The form at the top of the screen allows a template to be loaded; the main form allows the template to be modified before it is sent.

### Embedding Images in Email

The Markdown syntax \!\[alt_text](image_url) is a simple way to include images. They are displayed as a block, i.e. text does not wrap alongside them, and at full size or, depending on the email client, scaled to occupy the available display width.

Images can be stored in a static subfolder of your web server. For example <https://oxcamne.pythonanywhere.com/oxcam/static/images/middlesex_canal.jpg> is an OxCamNE example of an *image_url*. However it may well be preferable to store images somewhere such as on Google Drive.

Although Google Drive was not designed to be an image server, this can be done. You first make the image publicly available by right clicking, selecting share and then share again in the resulting menu, which produces a pop up box. If necessary, change General Access from 'Restricted' to 'Anyone with the link'. Then click Copy link followed by done. The saved link will be something like: <https://drive.google.com/file/d/1bPvuOwCA8BEwP1-s53Yc2zM1tru8rkaR/view?usp=sharing>. This includes an *image_id* `1bPvuOwCA8BEwP1-s53Yc2zM1tru8rkaR`.

You cannot use this Google Drive link directly, as it opens the image in google drive. Theoretically one should be able to construct an *image_url* as <https://drive.google.com/uc?export=view&id=image_id> but unfortunately at the time of writing many email clients will not display the image obtained this way (it is in SVG format).

Fortunately there is a [free web tool](https://www.labnol.org/embed/google/drive/) to convert the Google Drive link to one that does work. Open the tool and paste the google drive link into the top box (make sure to clear the box first). Then click Generate Embed Code, after dealing with the captcha. Click the button to copy the Direct Image Link, which is your *image_url* something like: <https://lh3.googleusercontent.com/drive-viewer/AKGpihZVuyjwH9QtlTk95UwU3Jzb_TSuM7FLrAYZqV3TIerHLWR57RkwnHrDOdteUiokJu6AJXSQ_Uo2luNK8nQ8vNsYWZAKO0Om5EA=s1600-rw-v1>.

You can use the *image_url* directly in Markdown, or if you want more complex formatting you can use html. You can set the image size (width) and make it a centered block, for example, thus:

```{{<img src="image_url" alt="alt_text" style="display: block; margin: auto; width:300px;"/>}}```

Or you might wish to have the image on the left with the following text alongside, separated by a margin:

```{{<img src="image_url" alt="alt_text" style="float: left; margin: 0 10px 10px 0; width: 300px;"/>}}```
