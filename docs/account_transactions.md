# [Oxford/Cambridge Alumni Group Application](index.md)

## Account Transactions Page

This page is reached from the link on a bank row in the [accounts page](accounts.md) (to display all transactions connected with the bank or payment processor), or through links in the Financial or Tax reports (to display related sets of transactions):

![transactions page](images/account_transactions.png)

The back link returns to the previous context. Transactions are displayed in a grid in reverse chronological order. You can click on a column header to sort by the values in that column, and click again to reverse sort order. For example, sorting by check number can help locate missing check records; click the ACC(rued) heading twice to see undeposited but recorded checks at the top.

The example shows bank transactions. The first two rows represent a check that reimbursed expenses for two different events and so has been split, as discussed later. Checks written to outside entities, as #873, do not reference a member. The transfer entry represents a funds transfer from Stripe, and the final entry illustrated represents a monthly payment to Pythonanywhere made by direct debit.

There is a search box at the top that allows transactions to be filtered, e.g. to specific accounts, members, and/or events, or by searching the Notes field for, e.g., name or email address.

The grid contains both Reconciled entries and manually entered Accrued entries. Reconciled entries are created by uploading transaction files obtained from the institution, which matches them up with accrued items in the case of bank checks or accrued charges, or with recorded charges in the case of membership dues or event registration payments made by members online using their credit/debit cards.

Accrued entries are created manually using the **+New button** when writing a check or making a purchase using the Society's bank credit/debit card. As noted above, the charge will be reconciled when the record of the charge or check deposit is later uploaded (reconciled).
Accrued entries can be edited/deleted. Checks should be recorded along with the check number, which will be used in reconciliation.

In the case where a check is written to reimburse expenses covering different events and/or account categories, first create an accrued record for the entire amount of the check, specifying the check number, payee member, and one of the event and account categories. Then split off the other event/account amounts by editing the original accrued record to show the amount to split off and the corresponding event/account category. This creates a new accrued record for the latter portion and reduces the amount in the original accrual accordingly. Any transaction fees will be divided proportionally.

There is no way to accrue for deposited incoming checks or charges, these should be allocated once they are uploaded from the institution (they will inititally be recorded as unallocated).

Editing an uploaded dues payment check by assigning to the 'membership dues' account and specifying the member automatically updates the member record Paiddate if necessary. Editing an event registration check by assigning it to the 'ticket sales' account and specifying both the member and the event associates it with the event registration which will now show as paid.

Uploaded transactions that need to be manually assigned can be split to assign portions of the amount to different accounts. To do this edit the transaction, specifying a split size and the associated account. A new transaction with the original characteristics and reduced amount will be created for the balance. Any transaction fee is divided proportionally.
