#!/usr/bin/env python3

# requires: pip3 install "textdistance[extras]"

import textdistance

def get_cosine_similarity(string1, string2):
    return textdistance.cosine.normalized_similarity(string1, string2)

import re

# requires: pip3 install langid laserembeddings
# and also: python3 -m laserembeddings download-models

from langid import classify
from laserembeddings import Laser

def get_vectors(strings):
    languages = []

    for string in strings:
        languages.append(classify(string)[0])

    corpus = [string.lower() for string in strings]
    corpus = [" ".join(string.splitlines()) for string in corpus]
    corpus = [re.sub(r'\W+', ' ', string) for string in corpus]

    return Laser().embed_sentences(corpus, lang=languages)

# requires: pip3 install sklearn

from sklearn.metrics.pairwise import cosine_similarity

def get_lasered_cosine_similarity(vector1, vector2):
    return cosine_similarity([vector1], [vector2])[0][0]

def formality(text):
    # list more restrictive patterns first
    formal = "(uint64_t\*?)|(_?[a-z]+(_[a-z]+)+)|('.')|(\d)|(\+)|(\-)|(\*)|(\/)|(%)|(\|)|(==)|(!=)|(<=)|(<)|(>=)|(>)|(=)|(lui)|(addi)|(ld)|(sd)|(add)|(sub)|(mul)|(divu)|(remu)|(sltu)|(beq)|(jalr)|(jal)|(ecall)"
    return len(re.findall(formal, text, re.IGNORECASE))

class Student:
    def __init__(self, firstname, lastname, q_total, q_length, q_formality, a_total, a_length, a_formality):
        self.number_of_qas = 1
        self.firstname     = firstname
        self.lastname      = lastname
        self.q_total       = q_total
        self.q_length      = q_length
        self.q_formality   = q_formality
        self.q_similarity  = float(0)
        self.a_total       = a_total
        self.a_length      = a_length
        self.a_formality   = a_formality
        self.a_similarity  = float(0)

import csv

def read_old_qas(responses_files):
    emails     = []
    firstnames = []
    lastnames  = []
    questions  = []
    answers    = []

    for responses_file in responses_files:
        with open(responses_file, mode='r') as csv_file:
            print(f'Considering as old responses file: {responses_file}')

            csv_reader = csv.DictReader(csv_file)

            for row in csv_reader:
                emails.append(row['Username'])
                questions.append(row['Ask Question'])
                answers.append(row['Answer Question'])

                if 'Firstname' in csv_reader.fieldnames and 'Lastname' in csv_reader.fieldnames:
                    firstnames.append(row['Firstname'])
                    lastnames.append(row['Lastname'])
                else:
                    firstnames.append("")
                    lastnames.append("")

    return emails, firstnames, lastnames, questions, answers

def read_qas(csv_file):
    csv_reader = csv.DictReader(csv_file)

    students = dict()

    emails = []

    questions = []
    answers   = []

    q_length    = 0
    q_formality = 0

    a_length    = 0
    a_formality = 0

    for row in csv_reader:
        emails.append(row['Username'])

        questions.append(row['Ask Question'])
        q_length    += len(row['Ask Question'])
        q_formality += formality(row['Ask Question'])

        answers.append(row['Answer Question'])
        a_length    += len(row['Answer Question'])
        a_formality += formality(row['Answer Question'])

        if row['Username'] not in students:
            students[row['Username']] = Student(
                row['Firstname'],
                row['Lastname'],
                float(row['Grade Question']),
                len(row['Ask Question']),
                formality(row['Ask Question']),
                float(row['Grade Answer']),
                len(row['Answer Question']),
                formality(row['Answer Question']))
        else:
            students[row['Username']].number_of_qas += 1
            students[row['Username']].q_total       += float(row['Grade Question'])
            students[row['Username']].q_length      += len(row['Ask Question'])
            students[row['Username']].q_formality   += formality(row['Ask Question'])
            students[row['Username']].a_total       += float(row['Grade Answer'])
            students[row['Username']].a_length      += len(row['Answer Question'])
            students[row['Username']].a_formality   += formality(row['Answer Question'])

    return students, emails, questions, answers, q_length, q_formality, a_length, a_formality

def write_results(students, csv_file):
    fieldnames = 'Google Apps Email', 'Firstname', 'Lastname', 'Total Average', 'Number of Q&As', 'Length of Answers', 'Formality of Answers', 'Similarity of Answers', 'Length of Questions', 'Formality of Questions', 'Similarity of Questions', 'Totel Length of Q&As', 'Question Average', 'Answer Average'

    csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

    csv_writer.writeheader()

    for student in students.items():
        csv_writer.writerow({
            'Google Apps Email': student[0],
            'Firstname': student[1].firstname,
            'Lastname': student[1].lastname,
            'Total Average': (student[1].q_total + student[1].a_total) / student[1].number_of_qas / 2,
            'Number of Q&As': student[1].number_of_qas,
            'Length of Answers': student[1].a_length,
            'Formality of Answers': student[1].a_formality,
            'Similarity of Answers': student[1].a_similarity,
            'Length of Questions': student[1].q_length,
            'Formality of Questions': student[1].q_formality,
            'Similarity of Questions': student[1].q_similarity,
            'Totel Length of Q&As': student[1].q_length + student[1].a_length,
            'Question Average': student[1].q_total / student[1].number_of_qas,
            'Answer Average': student[1].a_total / student[1].number_of_qas
        })

def compute_similarity(students, emails, message, strings, old_strings, old_emails, old_firstnames, old_lastnames):
    all_strings = strings + old_strings

    vectors = get_vectors(all_strings)

    similarity = [ [float(0)] * len(all_strings) for i in range(len(strings)) ]

    for x in range(len(strings)):
        for y in range(len(all_strings)):
            if x < y:
                # similarity[x][y] = get_cosine_similarity(strings[x], all_strings[y])
                similarity[x][y] = get_lasered_cosine_similarity(vectors[x], vectors[y])

                if similarity[x][y] > 0.95:
                    print(f'{message} similarity {similarity[x][y]} at [{x},{y}]:')
                    print(f'{emails[x]} ({students[emails[x]].firstname} {students[emails[x]].lastname})')
                    if y <= len(strings):
                        print(f'{emails[y]} ({students[emails[y]].firstname} {students[emails[y]].lastname})')
                    else:
                        print(f'{old_emails[y - len(strings)]} ({old_firstnames[y - len(strings)]} {old_lastnames[y - len(strings)]}) [old response]')
                    print(f'<<<\n{strings[x]}\n---\n{all_strings[y]}\n>>>\n')
            elif x > y:
                similarity[x][y] = similarity[y][x]
            else:
                similarity[x][y] = 1.0

    return similarity

def assign_similarity(students, emails, old_emails, q_similarity, a_similarity):
    all_emails = emails + old_emails

    for x in range(len(emails)):
        student = students[emails[x]]

        for y in range(len(all_emails)):
            if x != y:
                student.q_similarity += q_similarity[x][y]
                student.a_similarity += a_similarity[x][y]

        if (len(all_emails) > 1):
            # normalize again
            student.q_similarity /= len(all_emails) - 1
            student.a_similarity /= len(all_emails) - 1

def process_files(old_responses_files, responses_file, analysis_file):
    old_emails, old_firstnames, old_lastnames, old_questions, old_answers = read_old_qas(old_responses_files)

    students, emails, questions, answers, q_length, q_formality, a_length, a_formality = read_qas(responses_file)

    q_similarity = compute_similarity(students, emails, "Question", questions, old_questions, old_emails, old_firstnames, old_lastnames)
    a_similarity = compute_similarity(students, emails, "Answer", answers, old_answers, old_emails, old_firstnames, old_lastnames)

    assign_similarity(students, emails, old_emails, q_similarity, a_similarity)

    write_results(students, analysis_file)

    print(f'Number of students: {len(students)}')
    print(f'Total number of Q&As {len(questions)}')
    print(f'Average number of Q&As per student: {len(questions) / len(students)}')
    print(f'Average length of answers per student: {a_length / len(students)}')
    print(f'Average formality of answers per student: {a_formality / len(students)}')
    print(f'Average length of questions per student: {q_length / len(students)}')
    print(f'Average formality of questions per student: {q_formality / len(students)}')
    print(f'Average length of Q&As per student: {(q_length + a_length) / len(students)}')

import sys, getopt

def main(argv):
    old_responses_files = []

    response_file = ''
    analysis_file = ''

    try:
        opts, args = getopt.getopt(argv,"ho:r:a:",["ofile=","rfile=","afile="])
    except getopt.GetoptError:
        print ('examr.py { -o <oldresponsesfile> } -r <responsefile> -a <analysisfile>')
        sys.exit(2)

    for opt, arg in opts:
        if opt == '-h':
            print ('examr.py { -o <oldresponsesfile> } -r <responsefile> -a <analysisfile>')
            sys.exit()
        elif opt in ("-o", "--ofile"):
            old_responses_files.append(arg)
        elif opt in ("-r", "--rfile"):
            response_file = arg
        elif opt in ("-a", "--afile"):
            analysis_file = arg

    if response_file != '':
        with open(response_file, mode='r') as csv_responses_file:
            if analysis_file != '':
                with open(analysis_file, mode='w') as csv_analysis_file:
                    process_files(old_responses_files, csv_responses_file, csv_analysis_file)

if __name__ == "__main__":
    main(sys.argv[1:])