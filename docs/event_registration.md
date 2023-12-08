# [Oxford/Cambridge Alumni Group Database](index.md)

## Event Registration

This page displays the full information about a member's event registration including guests. It can be reached either through the [reservation list](reservation_list.md) or through the [member reservations](member_reservations.md) page:

![top](images/event_registration.png)

The **back** link will take you back to the events page.

Links allow you to send email to the member, or to pop out to view the member's record.

This page can be used to build a reservation on a member's behalf (e.g. for a speaker), as well as to view/edit reservations made by the members themselves.

Note that you can drill down to edit the individual guest, and delete guests. If there are no additional guests, you can delete the member's own registration.

If a member pays for an event by check, you would edit the member's reservation (first row) to record the check payment by updating the 'paid' field.

### Managing Event Registrations

First note that each individual attendee or potential attendee of an event, whether member or guest, is represented by an individual record in the 'Reservations' table. The members complete registation including their guests is thus shown as a grid of individually addressable records. The member's own record, known as the host registration, is always shown first in the grid. All the records in a reservation refer to the member's record in the 'Members' table. The member record may represent an actual member, someone who has simply joined our mailing list, or an alum or member of a sponsoring institution (e.g. an 'Ancient University' alum) registering for an event.

Every individual guest reservation is in one of three states:

- Provisional/unconfirmed: the host registering has not yet checked out. A place has not yet been allocated.

- Waitlisted: the host has checked out, but a place was not available. An email

- Confirmed: the host has checked out and a place has been allocated. An email confirmation is sent to the member once any necessary payment has been made.

A confirmed registration may not yet have been paid for (assuming there is a charge). The host member can revisit the registration link later and checkout again to make payment.

### Building the Waitlist

When a host member checks out a new reservation that would exceed the event capacity, the entire reservation is waitlisted: both the host and any guest reservation records have 'Waitlist' set true.

However, a confirmed reservation can also contain additional guests in the provisional or waitlisted states. For example, the host may return and add an additional guest and not have checked out or paid, or there may not be space for the additional guest(s).

To view the waitlist, click on the event name in the Events Page to display the Reservations List, then click on the 'waitlist' link. The waitlist is displayed in chronological order. This will include all reservations that include any waitlisted guests.

Note that if there is a limited number of tickets of a particular ticket type, there may be a waitlist even though the event is not full.

### Allocating Available Spaces to the Waitlist

If spaces become available, the Secretary or other official managing registration will determine how to allocate them, normally starting at the top of the waitlist.

It is **important not to delete** the cancelled registrations until efforts to re-sell them to the waitlist have failed, otherwise members not on the waitlist might grab them. You might use the notes to document that they need to be cancelled later.

When someone on the waitlist is found who can use the freed places, allocate the spaces by clearing the 'waitlist' flag. If it is a reservation that is entirely waitlisted, simply edit the host reservation (first row). In the case of a waitlisted additional guest, edit the individual waitlisted row(s). The member should then revisit the booking link and checkout, making payment and receiving confirmation.

Depending on how close the event is, one can offer places to a single waitlistee, or to a whole group on a first-come first-serve basis.

The Reservation Display includes a link to email the host member. You can include '\<reservation>' at the bottom of the text to include a confirmation of the registration. If a payment is needed, this will show the amount and also include the payment link.
