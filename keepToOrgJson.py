#!/usr/bin/env python3

import os
from os.path import exists
import html
import sys
import datetime
import json
import argparse
from shutil import copy2

"""
KeepToOrg.py

Usage:
    python KeepToOrg.py /path/to/google/Keep output/dir

Given a Takeout of your Google Keep Notes in .html format, output .org files with logical groupings
based on tags. This will also format lists and try to be smart.
"""

# TODO:
# Format links:
#   Links have the syntax [[https://blah][Example link]] (things can be internal links too!)
#   See https://orgmode.org/manual/External-links.html

# Convert an array of tags to an Emacs Org tag string
# Tags have the syntax :tag: or :tag1:tag2:

def tagsToOrgString(tags):
    if len(tags) == 0:
        return ""

    tagString = ":"
    for tag in tags:
        tagString += tag + ":"

    return tagString


class Note:
    def __init__(self):
        self.title = ""
        self.body = ""
        self.tags = []
        self.archived = False
        # If no date can be parsed, set it to Jan 1, 2000
        self.date = datetime.datetime(2000, 1, 1)
        self.images = []

    def toOrgString(self):
        # status = '(archived) ' if self.archived else ''
        # Create a copy so we can mangle it
        body = self.body
        title = self.title

        # Convert lists to org lists. This is a total hack but works
        body = body.replace(
            '<li class="listitem"><span class="bullet">&#9744;</span>\n', "- [ ] "
        )
        body = body.replace(
            '<li class="listitem checked"><span class="bullet">&#9745;</span>', "- [X] "
        )
        # Flat out remove these
        for htmlTagToErase in [
            '<span class="text">',
            "</span>",
            "</li>",
            '<ul class="list">',
            "</ul>",
        ]:
            body = body.replace(htmlTagToErase, "")
        # This is very weird, but fix the edge case where the list entry has a new line before the content
        for listTypeToFixNewLines in ["- [ ] \n", "- [X] \n"]:
            body = body.replace(listTypeToFixNewLines, listTypeToFixNewLines[:-1])

        # Unescape all (e.g. remove &quot and replace with ")
        title = html.unescape(title)
        body = html.unescape(body)
        for i, tag in enumerate(self.tags):
            self.tags[i] = html.unescape(tag)

        # Strip tags
        for tag in self.tags:
            body = body.replace("#{}".format(tag), "")

        # add image links:
        imageLinks = ["[[file:" + place + "]]" for place in self.images]
        
        
        # Remove any leading/trailing whitespace (possibly leftover from tags stripping)
        body = body.strip()
        body += ("\n".join(imageLinks))

        # Make a title if necessary
        orgTitle = title
        if not orgTitle:
            toNewline = body.find("\n")
            # If there's a line break; use the first line as a title
            if toNewline >= 0:
                orgTitle = body[:toNewline]
                body = body[len(orgTitle) + 1 :]
            # The note has no breaks; make the body the title
            else:
                orgTitle = body
                # If the title is the whole body, clear the body
                body = ""

        nesting = "*" if self.archived else ""
        # Various levels of information require different formats
        created = self.date.strftime(
            ":PROPERTIES:\n:CREATED:  [%Y-%m-%d %a %H:%M]\n:END:"
        )
        if body or len(self.tags):
            if body and not len(self.tags):
                return "*{} {}\n{}\n{}".format(nesting, orgTitle, created, body)
            if not body and len(self.tags):
                return "*{} {} {}\n{}\n".format(
                    nesting, orgTitle, tagsToOrgString(self.tags), created
                )
            else:
                return "*{} {} {}\n{}\n{}\n".format(
                    nesting, orgTitle, body, tagsToOrgString(self.tags), created
                )
        # If no body nor tags, note should be a single line
        else:
            return "*{} {}\n{}".format(nesting, orgTitle, created)


def getAllNoteHtmlFiles(htmlDir):
    print("Looking for notes in {}".format(htmlDir))
    noteHtmlFiles = []
    jsonFiles = []
    for root, dirs, files in os.walk(htmlDir):
        for file in files:
            ending = ".json"
            if file.endswith(ending):
                jsonFiles.append(os.path.join(root, file))
    print("Found {} notes".format(len(jsonFiles)))

    return jsonFiles


def getHtmlValueIfMatches(line, tag, endTag):
    if tag.lower() in line.lower() and endTag.lower() in line.lower():
        return line[line.find(tag) + len(tag) : -(len(endTag) + 1)], True

    return "", False


def makeSafeFilename(strToPurify):
    strToPurify = strToPurify.replace("/", "")
    strToPurify = strToPurify.replace(".", "")
    return strToPurify


def main(keepHtmlDir, outputDir, includeArchived, splitByTag):
    jsonFiles = getAllNoteHtmlFiles(keepHtmlDir)

    noteGroups = {}

    for i, jsonFile in enumerate(jsonFiles):
        # Read in the file

        jsonFile = open(jsonFile, "r")
        jsonString = jsonFile.read()
        jsonFile.close()
        meta_data = json.loads(jsonString)

        note = Note()

        if meta_data["isArchived"] or meta_data["isTrashed"]: # Treat trashed notes as archived (maybe ignore them instead?)
            note.archived = True
        note.date = datetime.datetime.fromtimestamp(
            meta_data["createdTimestampUsec"] / 1000000.0
        )

        if meta_data["title"]:
            note.title = meta_data["title"]
        
        if "textContent" in meta_data:
            note.body = meta_data["textContent"]

        elif "listContent" in meta_data:
            print(meta_data["listContent"])
            text = "\n".join([x['text'] for x in meta_data["listContent"]])
            note.body = f"List:\n{text}"
        else:
            raise Exception("No textContent or listContent in note")
        
        # TODO: consider copying images to target file
        if "attachments" in meta_data:
            for attachment in meta_data["attachments"]:
                if exists(os.path.join(keepHtmlDir, attachment["filePath"])):
                    copy2(os.path.join(keepHtmlDir, attachment["filePath"]),outputDir)
                elif exists(os.path.join(keepHtmlDir, attachment["filePath"][:-3]+"jpg")):
                    copy2(os.path.join(keepHtmlDir, attachment["filePath"][:-3]+"jpg"),outputDir) 
                elif exists(os.path.join(keepHtmlDir, attachment["filePath"][:-3]+"jpeg")):
                    copy2(os.path.join(keepHtmlDir, attachment["filePath"][:-3]+"jpeg"),outputDir) 
                note.images.append(attachment["filePath"])
        
        if splitByTag:
            for tag in note.tags: 
                if tag in noteGroups:
                    noteGroups[tag].append(note)
                else:
                    noteGroups[tag] = [note]

        if not note.tags:
            if "Untagged" in noteGroups:
                noteGroups["Untagged"].append(note)
            else:
                noteGroups["Untagged"] = [note]


    numNotesWritten = 0
    for tag, group in noteGroups.items():
        outFileName = "{}/{}.org".format(outputDir, makeSafeFilename(tag))

        notesSortedByDate = sorted(group, key=lambda note: note.date)
        # If capture etc. appends, we should probably follow that same logic (don't reverse)
        # notesSortedByDate.reverse()

        # Concatenate all notes into lines
        lines = []
        archivedLines = []
        for note in notesSortedByDate:
            if note.archived:
                archivedLines.append(note.toOrgString() + "\n")
            else:
                lines.append(note.toOrgString() + "\n")

        if len(archivedLines) and includeArchived:
            lines = ["* *Archived*\n"] + archivedLines + lines

        outFile = open(outFileName, "w")
        outFile.writelines(lines)
        outFile.close()
        print("Wrote {} notes to {}".format(len(group), outFileName))
        numNotesWritten += len(group)

    print("Wrote {} notes total".format(numNotesWritten))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("keepHtmlDir", help="Path to the directory containing the Keep HTML files")
    parser.add_argument("outputDir", help="Path to the directory where the output Org files should be written")
    parser.add_argument("--includeArchived", help="Whether to include archived and deleted notes in the output", type=bool, default=False, required=False)
    parser.add_argument("--splitByTag", help="Whether to split notes by tag", type=bool, default=False, required=False)
    args = parser.parse_args()

    keepHtmlDir = args.keepHtmlDir
    outputDir = args.outputDir
    main(keepHtmlDir, outputDir, args.includeArchived, args.splitByTag)
