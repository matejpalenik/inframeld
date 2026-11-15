# Document fixtures

`alice-in-wonderland.pdf` is a one-page, text-based test document with a short excerpt from Chapter I of Lewis Carroll’s _Alice’s Adventures in Wonderland_. It was rendered locally with ReportLab using PDF's standard Helvetica fonts. [Project Gutenberg eBook #11](https://www.gutenberg.org/ebooks/11) identifies the edition as public domain in the United States.

The storage integration test checks the exact PDF bytes after staging and resuming the original allocation. For text extraction, the expected line on page 1 is `Oh dear! Oh dear! I shall be late!`. Tests read the fixture from the checkout.
