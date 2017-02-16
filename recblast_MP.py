import os
import sys

lib_path = os.path.abspath(os.path.join('..', 'Misc'))
sys.path.append(lib_path)

import multiprocessing

from BioSQL import BioSeqDatabase

from Misc.misc_code import biosql_DBSeqRecord_to_SeqRecord, blast, merge_ranges


def biosql_seq_lookup_cascade(dtbase, sub_db_name, id_type, identifier, verbose=False):
    seqrec = None
    try_get_id = True
    if try_get_id:
        try:
            if verbose:
                print("Now searching database {0} for {1}: {2}".format(sub_db_name, id_type, identifier))
            seqrec = biosql_DBSeqRecord_to_SeqRecord(dtbase.lookup(**{id_type: identifier}))
            if verbose:
                print('Got sequence for {}!'.format(identifier))
            try_get_id = False
        except IndexError as err:
            if verbose:
                print("WARNING: couldn't find {0} using given ID type... \n Full error: {1}".format(identifier, err))
    if try_get_id:
        identifier_sans_subnumber = identifier.split('.')[0]
        if verbose:
            print('Seeing if removing any sub-numbers (acc: xxxxxx.1 for example) helps...')
            print('Identifier: ', identifier_sans_subnumber)
        try:
            if verbose:
                print("Now searching database {0} for {1}: {2}".format(sub_db_name, id_type,
                                                                       identifier_sans_subnumber))
            seqrec = biosql_DBSeqRecord_to_SeqRecord(dtbase.lookup(**{id_type: identifier_sans_subnumber}))
            if verbose:
                print('Got sequence for {}!'.format(identifier))
            try_get_id = False
        except IndexError as err1:
            if verbose:
                print("WARNING: couldn't find {0} using abbreviated ID... \n Full error: {1}"
                      .format(identifier_sans_subnumber,
                              err1))
    if try_get_id:
        try:
            if verbose:
                print('Attempting to search using Primary ID instead of declared type:')
            seqrec = biosql_DBSeqRecord_to_SeqRecord(dtbase.lookup(primary_id=identifier))
            if verbose:
                print('Got sequence for {}!'.format(identifier))
            try_get_id = False
        except IndexError as err2:
            if verbose:
                print("WARNING: couldn't find {0} using Primary ID... \n full error: {1}".format(identifier, err2))
    if try_get_id:
        try:
            if verbose:
                print('Attempting to search using name instead of declared type:')
            seqrec = biosql_DBSeqRecord_to_SeqRecord(dtbase.lookup(name=identifier))
            if verbose:
                print('Got sequence for {}!'.format(identifier))
            try_get_id = False
        except IndexError as err3:
            if verbose:
                print("WARNING: Still couldn't find {0} using name search: \n full error: {1}".format(identifier, err3))

    if try_get_id:
        try:
            id_type = input('Last shot, chose an ID type: '
                            '[accession, primary_id, gi, version, display_id, name]')
            if id_type == 'exit':
                exit(exit(), 'Script ended!')
            seqrec = biosql_DBSeqRecord_to_SeqRecord(dtbase.lookup(**{id_type: identifier}))
            if verbose:
                print('Got sequence for {}!'.format(identifier))
        except IndexError as err5:
            if verbose:
                print("WARNING: COULD NOT FIND SEQUENCES FOR ID:{0}: \n full error: {1}".format(identifier, err5))
    return seqrec


def biosql_get_record_mp(sub_db_name, passwd, id_list=list(), id_type='accession', driver="psycopg2", user="postgres",
                         host="localhost", db="bioseqdb", num_proc=2, verbose=True):
    """

    :param sub_db_name:
    :param passwd:
    :param id_list:
    :param id_type:
    :param driver:
    :param user:
    :param host:
    :param db:
    :param num_proc:
    :param verbose:
    :return:
    if __name__ == '__main__':
        biosql_get_record_mp(sub_db_name='MyoLuc2.0', passwd='',
                             id_list=['NW_005871148', 'NW_005871300', 'NW_005871148'], id_type='accession',
                             driver="psycopg2", user="postgres",
                             host="localhost", db="bioseqdb", verbose=True)
    """

    class GetSeqMP(multiprocessing.Process):
        def __init__(self, task_queue, result_queue, db, host, driver, user, passwd, sub_db_name, verbose):
            multiprocessing.Process.__init__(self)
            self.task_queue = task_queue
            self.result_queue = result_queue
            self.db = db
            self.host = host
            self.driver = driver
            self.user = user
            self.password = passwd
            self.sub_db_name = sub_db_name
            self.verbose = verbose
            self.server = BioSeqDatabase.open_database(driver=self.driver, user=self.user, passwd=self.password,
                                                       host=self.host, db=self.db)

        # Understand this better
        def run(self):
            proc_name = self.name
            while True:
                next_task = self.task_queue.get()
                if next_task is None:
                    if self.verbose:
                        print('Tasks Complete')
                    self.task_queue.task_done()
                    break
                answer = next_task(connection=self.server, sub_db_name=self.sub_db_name)
                self.task_queue.task_done()
                self.result_queue.put(answer)

    class BioSeqLookupCascade(object):
        def __init__(self, id_type, identifier, verbose):
            self.id_type = id_type
            self.identifier = identifier
            self.verbose = verbose

        def __call__(self, sub_db_name, connection):
            server = connection
            dtbase = server[sub_db_name]
            seqrec = biosql_seq_lookup_cascade(dtbase=dtbase, sub_db_name=sub_db_name, id_type=self.id_type,
                                               identifier=self.identifier, verbose=self.verbose)
            return self.identifier, seqrec

        # def __str__(self):
        #    return 'ARC'

        def run(self):
            if self.verbose:
                print('Fetching sequence: ', self.identifier)

    idents = multiprocessing.JoinableQueue()
    results = multiprocessing.Queue()

    # num = multiprocessing.cpu_count() * 2

    num_jobs = len(id_list)
    seqdict = dict()
    getseqs = [GetSeqMP(idents, results, db=db, host=host, driver=driver, user=user, passwd=passwd,
                        sub_db_name=sub_db_name, verbose=verbose) for i in range(num_proc)]
    for gs in getseqs:
        gs.start()

    for i in range(num_jobs):
        idents.put(BioSeqLookupCascade(id_type=id_type, identifier=id_list[i], verbose=verbose))

    for i in range(num_proc):
        idents.put(None)

    while num_jobs:
        temp = results.get()
        print(temp)
        seqdict[temp[0]] = temp[1]
        num_jobs -= 1
    return seqdict


def fetchseqMP(id_file, species, email='', source="psql", output_type="fasta", output_name="outfile",
               db="nucleotide", delim='\t', id_type='accession', batch_size=50, passwd='', version='1.0', verbose=True,
               n_threads=2):
    class FetchSeqMP(multiprocessing.Process):
        def __init__(self, id_queue, seq_out_queue, lock):
            multiprocessing.Process.__init__(self)
            self.id_queue = id_queue
            self.seq_out_queue = seq_out_queue
            self.lock = lock

        def run(self):  # The meat of the script
            while True:
                fs_instance = self.id_queue.get()
                if fs_instance is None:
                    self.id_queue.task_done()
                    break
                output = fs_instance(lock=self.lock)
                self.id_queue.task_done()
                self.seq_out_queue.put(output)
            return

    class FetchSeq(object):  # Todo: Split this up into smaller parts, cause this is too huge.
        def __init__(self, seq_id, species, email, source, output_type, output_name, db, version,
                     delim, id_type, batch_size, passwd, verbose):
            self.species = species
            self.email = email
            self.source = source
            self.output_type = output_type
            self.output_name = output_type
            self.db = db
            self.version = version
            self.delim = delim
            self.id_type = id_type
            self.batch_size = batch_size
            self.passwd = passwd

        def __call__(self, lock=None):

            import re
            from os import strerror
            from errno import ENOENT
            from Bio import SeqIO
            from pathlib import Path

            out_file = Path(output_name + '.' + output_type)
            if verbose:
                print("Loading ID File...")
            if in_file.exists():
                if verbose:
                    print('ID File found successfully: ', str(in_file.absolute()))
            else:
                raise FileNotFoundError(ENOENT, strerror(ENOENT), str(in_file.name))

            # Read ID file to compile lists:
            with in_file.open('r') as infile_handle:
                if verbose:
                    print('Reading ID File...')
                id_prelist = [line.strip() for line in infile_handle]  # list of each line in the file
                id_prelist = list(filter(None, id_prelist))
                if verbose:
                    print('Full header for Entry 1:')
                    try:
                        print(id_prelist[0])
                    except IndexError:
                        print('No items found!')
                        raise
            # Check to make sure list is not empty
            if verbose and (not id_prelist or id_prelist is None):
                print('id_prelist is empty!')

            id_list = [str(item.split(delim)) for item in id_prelist]  # Breaks the tab sep in the lines into strings

            # Define the regex functions
            p = [re.compile('(gi)([| :_]+)(\d\d+\.?\d*)(.*)'),  # regex for gi
                 re.compile('([AXNYZ][MWRCPGTZ]|ref)([| _:]+)(\d\d+\.?\d*)(.*)'),  # regex for accession
                 re.compile('(id)([| :_]+)(\d\d+\.?\d*)(.*)'),  # regex for generic ID
                 re.compile(':(\d+)-(\d+)'),  # regex for sequence range
                 ]
            id_list_ids = []  # Initialized list of IDs
            seq_range = {}  # Initialized dict of sequence ranges

            # Begin search:
            if verbose:
                print('ID File Loaded, performing regex search for identifiers...')
                print('ID Specified as: ', id_type)
            if id_type == 'brute':
                if bool(p[1].findall(id_list[0])):
                    id_type = 'accession'
                    if verbose:
                        print(p[1].findall(id_list[0]))
                elif bool(p[0].findall(id_list[0])):
                    id_type = 'gi'
                    if verbose:
                        print(p[1].findall(id_list[0]))
                elif bool(p[2].findall(id_list[0])):
                    id_type = 'id'
                    if verbose:
                        print(p[1].findall(id_list[0]))
                else:
                    id_type = 'other'
                if verbose:
                    print('Brute Force was set, tested strings for all pre-registered IDs. ID was selected as type ',
                          id_type)
            if id_type == 'gi':
                if bool(p[0].findall(id_list[0])):
                    found_id = True
                    if verbose:
                        print('Successfully found GI numbers, compiling list!')
                    for item in id_list:
                        item_parts = p[0].findall(item)
                        if verbose:
                            print('Item:\t', item_parts)
                        id_list_ids.append(item_parts[0][0:3])
                        if bool(p[3].findall(id_list[0])):
                            # Seq_range will be a list of tuples where the second element is the range, and the first
                            # is the ID. This way, the function accommodates sequences with a subrange and sequences without a
                            # subrange.
                            seq_range[''.join(p[0].findall(item)[0][0:3])] = p[3].findall(item)[0]
                            if verbose:
                                print('Found sequence delimiters in IDs!')
                else:
                    found_id = False
            elif id_type == 'accession':
                if bool(p[1].findall(id_list[0])):
                    found_id = True
                    if verbose:
                        print('Successfully found accession numbers, compiling list!')
                    for item in id_list:
                        item_parts = p[1].findall(item)
                        if verbose:
                            print('Item:\t', item_parts)
                        id_list_ids.append(item_parts[0][0:3])
                        if bool(p[3].findall(id_list[0])):
                            seq_range[''.join(p[1].findall(item)[0][0:3])] = p[3].findall(item)[0]
                            if verbose:
                                print('Found sequence delimiters in IDs!')
                else:
                    found_id = False
            elif id_type == 'id':
                if bool(p[2].findall(id_list[0])):
                    found_id = True
                    if verbose:
                        print('Successfully found ID numbers, compiling list!')
                    for item in id_list:
                        item_parts = p[2].findall(item)
                        if verbose:
                            print('Item:\t', item_parts)
                        id_list_ids.append(item_parts[0][0:3])
                        if bool(p[3].findall(id_list[0])):
                            seq_range[''.join(p[2].findall(item)[0][0:3])] = p[3].findall(item)[0]
                            if verbose:
                                print('Found sequence delimiters in IDs!')
                else:
                    found_id = False
            else:
                found_id = False
            while not found_id:
                print('Header identified for first sequence ID:', id_list[0], sep='\n')
                custom_regex = input(
                    'Couldn\'t find ID using preset patterns... Please enter ID pattern for regex search:')
                if custom_regex[0].lower() == 'q':
                    exit()
                print('Will try again...')
                p.append(re.compile(custom_regex))
                if bool(p[4].findall(id_list[0])):
                    id_type = input('ID name:')
                    found_id = True
                    if verbose:
                        print('Successfully found custom ID numbers, compiling list!')
                    for item in id_list:
                        item_parts = p[4].findall(item)
                        if verbose:
                            print('Item:\t', item_parts)
                        id_list_ids.append(item_parts[0][0:3])
                        if bool(p[3].findall(str(item))):
                            seq_range[''.join(p[4].findall(item)[0][0:3])] = p[3].findall(item)[0]
                            if verbose:
                                print('Found sequence delimiters in IDs!')
                else:
                    print('Sorry, still can\'t find it...')
            if verbose:
                print('ID list: ')
                for index, ID_item in enumerate(id_list_ids):
                    print(index + 1, ': ', ''.join(ID_item))

            # Armed with the ID list, we fetch the sequences from the appropriate source
            if source.lower() == "entrez":  # Todo: Make sure this will actually output the correct sequence range...
                if verbose:
                    print('Source selected was Entrez. Beginning search now:')
                from Bio import Entrez
                from urllib.error import HTTPError
                from time import sleep
                Entrez.email = email
                if verbose:
                    print('Entrez email set as: ', email)
                id_str = ",".join([i[2] for i in id_list_ids])
                search_results = Entrez.read(Entrez.epost(db, id=id_str))
                if verbose:
                    print('EPost with IDs for database {} submitted to Entrez'.format(db))
                webenv = search_results["WebEnv"]
                query_key = search_results["QueryKey"]
                with out_file.open("a+") as out_handle:
                    if verbose:
                        print('Opened outfile ', str(out_file.name))
                        print('Commencing download:')
                    for start in range(0, len(id_list_ids), batch_size):
                        if verbose:
                            print('Fetching sequences {0}-{1}'.format(start, start + batch_size))
                        attempt = 0
                        while attempt < 3:
                            if verbose:
                                print('Attempt #', str(attempt + 1))
                            attempt += 1
                            try:
                                fetch_handle = Entrez.efetch(db=db, rettype="fasta", retmode="text", retstart=start,
                                                             retmax=batch_size, webenv=webenv, query_key=query_key)
                            except HTTPError as err:
                                if 500 <= err.code <= 599:
                                    print("Received error from server ", err)
                                    print("Attempt {} of 3".format(attempt))
                                    print('Will wait before next attempt...')
                                    sleep(15)
                                else:
                                    print('could\'t get sequences, omitting', id_list[start:start + batch_size])
                                    success_status = 0
                                    continue
                        data = fetch_handle.read()
                        fetch_handle.close()
                        out_handle.write(data)
            elif source.lower() == "psql":
                if verbose:
                    print('Searching for sequences in local PostgreSQL db...')
                sub_db_name = ''.join([i[0:3] for i in species.title().split(' ')]) + version
                id_list_search = [''.join(i[0:3]) for i in id_list_ids]
                seqdict = biosql_getrecord(sub_db_name=sub_db_name, id_list=id_list_search, id_type=id_type,
                                           passwd=passwd, driver="psycopg2", user="postgres", host="localhost",
                                           db="bioseqdb",
                                           parallel=parallel, verbose=verbose)
                itemsnotfound = [''.join(x) for x in id_list_ids if ''.join(x) not in seqdict.keys()]
                if itemsnotfound:
                    if verbose:
                        print(
                            'Some items were not found. List of items will be saved to the file items_not_found.output')
                        for item in itemsnotfound:
                            print(item)
                    with open(str(out_file.cwd()) + 'items_not_found.output', 'w') as missingitems:
                        missingitems.writelines(itemsnotfound)
                keys = [k for k in seqdict.keys()]
                if verbose:
                    print("Sequence Dictionary keys:")
                    print(keys)
                if bool(seq_range):
                    seqrange_ids = [ids for ids in seq_range.keys()]
                    if verbose:
                        print('Sequence Range IDs:')
                        print(seqrange_ids)
                    for k in keys:
                        if seqdict[k].id in seqrange_ids:
                            if verbose:
                                print('For sequence {}, found a sequence range!'.format(str(seqdict[k].id)))
                                print('Full length of sequence: {}'.format(len(seqdict[k])))
                            if id_type == 'gi':
                                seq_description_full = p[0].findall(seqdict[k].description)[0]
                            elif id_type == 'accession':
                                seq_description_full = p[1].findall(seqdict[k].description)[0]
                            elif id_type == 'id':
                                seq_description_full = p[2].findall(seqdict[k].description)[0]
                            else:
                                seq_description_full = p[4].findall(seqdict[k].description)[0]
                        else:
                            if verbose:
                                print('No sequence range found, continuing...')
                            continue
                        id_range = ':' + '-'.join(seq_range[k])
                        if int(seq_range[k][0]) > int(seq_range[k][1]):
                            tmp_id = seqdict[k].id
                            tmp_name = seqdict[k].name
                            tmp_desc = seqdict[k].description
                            tmp_dbxrefs = seqdict[k].dbxrefs
                            tmp_feat = seqdict[k].features
                            tmp_annotations = seqdict[k].annotations
                            tmp_let_anno = seqdict[k].letter_annotations
                            seqdict[k].seq = seqdict[k][
                                             int(seq_range[k][1]):int(seq_range[k][0])].seq.reverse_complement()

                        else:
                            seqdict[k] = seqdict[k][int(seq_range[k][0]):int(seq_range[k][1])]
                        if verbose:
                            print('Seq_description_full: ', seq_description_full)
                            print('id_range: ', id_range[1:])
                        if int(seq_range[k][0]) > int(seq_range[k][1]):
                            seqdict[k].description = ''.join(seq_description_full[0:3]) + id_range + '(-)' + \
                                                     str(seq_description_full[3])
                        else:
                            seqdict[k].description = ''.join(seq_description_full[0:3]) + id_range + '(+)' + \
                                                     str(seq_description_full[3])
                        if verbose:
                            print('Sequence Description: \n\t', seqdict[k].description)
                        seqdict[k].id += id_range
                        if verbose:
                            print('Sequence ID: \n\t', seqdict[k].id)
                            if id_range:
                                print('Length of subsequence with range {0}: {1}'.format(id_range, len(seqdict[k])))
                if verbose:
                    print('Sequence Record post-processing, to be saved:')
                    print(seqdict)

                SeqIO.write([seqdict[key] for key in seqdict.keys()], str(out_file), output_type)
            elif source == "fasta":  # Note: anecdotally, this doesn't run terribly fast - try to avoid.
                seqdict = SeqIO.index(db, source,
                                      key_function=lambda identifier: p[0].search(
                                          p[2].search(identifier).group()).group())
                itemsnotfound = [x for x in id_list_ids if x not in seqdict.keys()]
                if itemsnotfound:
                    if verbose:
                        print(
                            'Some items were not found. List of items will be saved to the file items_not_found.output')
                        for item in itemsnotfound:
                            print(item)
                    with open(str(out_file.cwd()) + 'items_not_found.output', 'w') as missingitems:
                        missingitems.writelines(itemsnotfound)
                keys = [k for k in seqdict.keys()]
                if verbose:
                    print("Sequence Dictionary keys:")
                    print(keys)
                if bool(seq_range):
                    seqrange_ids = [ids for ids in seq_range.keys()]
                    if verbose:
                        print('Sequence Range IDs:')
                        print(seqrange_ids)
                    for k in keys:
                        if seqdict[k].id in seqrange_ids:
                            if verbose:
                                print('For sequence {}, found a sequence range!'.format(str(seqdict[k].id)))
                                print('\tFull length of sequence: {}'.format(len(seqdict[k])))
                            if id_type == 'gi':
                                seq_description_full = p[0].findall(seqdict[k].description)[0]
                            elif id_type == 'accession':
                                seq_description_full = p[1].findall(seqdict[k].description)[0]
                            elif id_type == 'id':
                                seq_description_full = p[2].findall(seqdict[k].description)[0]
                            else:
                                seq_description_full = p[4].findall(seqdict[k].description)[0]
                        if verbose:
                            print(int(seq_range[k][0]))
                            print(int(seq_range[k][1]))
                        id_range = ':' + '-'.join(seq_range[k])
                        seqdict[k] = seqdict[k][int(seq_range[k][0]):int(seq_range[k][1])]
                        seqdict[k].description = ''.join(seq_description_full[0:3]) + id_range + str(
                            seq_description_full[3])
                        seqdict[k].id += id_range
                        if verbose:
                            print('\tLength of subsequence with range{0}: {1}'.format(id_range, len(seqdict[k])))
                        else:
                            if verbose:
                                print('No sequence range found, continuing...')
                            continue

                SeqIO.write([seqdict[key] for key in seqdict.keys()], str(out_file), output_type)
            else:
                print('Not a valid database source!')
            if verbose:
                print('Done!')
            return success_status


class RecBlastMP_Thread(multiprocessing.Process):
    """
    RecBlast_MP_Thread_Handle is the first branch to be made. It will perform the actual RecBlast.
    """

    def __init__(self, proc_id, rb_queue, rb_results_queue, lock):
        multiprocessing.Process.__init__(self)
        self.name = proc_id
        self.rb_queue = rb_queue
        self.rb_results_queue = rb_results_queue
        self.lock = lock

    def run(self):  # The meat of the script
        while True:
            rb_instance = self.rb_queue.get()
            if rb_instance is None:
                self.rb_queue.task_done()
                break
            output = rb_instance(proc_id=self.name, lock=self.lock)
            self.rb_queue.task_done()
            self.rb_results_queue.put(output)
        return


class RecBlastContainer(object):
    def __init__(self, forward_blast_output, forward_blast_ids, recblast_output_unanno, reverse_blast_outputs,
                 reverse_blast_ids, recblast_annotated):
        self.fw_out = forward_blast_output
        self.fw_id = forward_blast_ids
        self.fs_out = recblast_output_unanno
        self.rv_outs = reverse_blast_outputs
        self.rv_ids = reverse_blast_ids
        self.recblast_annotated = recblast_annotated


class RecBlast(object):
    def __init__(self, seq_record, target_species, fw_blast_db, infile_type, output_type,
                 query_species, blast_type, local_blast_1, local_blast_2, rv_blast_db, expect, perc_score, perc_ident,
                 perc_length, megablast, email, id_type, fw_source, fw_id_db, fetch_batch_size, passwd,
                 fw_id_db_version, verbose, n_threads):
        self.seq_record = seq_record
        self.target_species = target_species
        self.fw_blast_db = fw_blast_db
        self.infile_type = infile_type
        self.output_type = output_type
        self.query_species = query_species
        self.blast_type = blast_type
        self.local_blast_1 = local_blast_1
        self.local_blast_2 = local_blast_2
        self.rv_blast_db = rv_blast_db
        self.expect = expect
        self.perc_score = perc_score
        self.perc_ident = perc_ident
        self.perc_length = perc_length
        self.megablast = megablast
        self.email = email
        self.id_type = id_type
        self.fw_source = fw_source
        self.fw_id_db = fw_id_db
        self.batch_size = fetch_batch_size
        self.passwd = passwd
        self.fw_id_db_version = fw_id_db_version
        self.verbose = verbose
        self.n_threads = n_threads
        # self.lock = lock
        # self.proc_id = proc_id

    def __call__(self, lock, proc_id):
        from pathlib import Path
        from Bio.Blast import NCBIXML
        if self.verbose:
            with lock:
                print('[Proc: {0}] [Seq.Name: {1}]'.format(proc_id, self.seq_record.name))
        if self.verbose > 1:
            with lock:
                print('\t Creating handles for intermediary outputs...')
        forward_blast_output = Path("{0}_recblast_out".format(self.target_species).replace(' ', '_') + '/' +
                                    "{0}_{1}_tmp".format(self.blast_type, self.seq_record.name).replace(' ',
                                                                                                        '_') + '/' +
                                    "{0}_{1}_{2}_to_{3}.xml".format(self.blast_type, self.seq_record.name,
                                                                    self.query_species, self.target_species).replace(
                                        ' ',
                                        '_')
                                    )

        forward_id_score_output = Path("{0}_recblast_out".format(self.target_species).replace(' ', '_') + '/' +
                                       "{0}_{1}_tmp".format(self.blast_type,
                                                            self.seq_record.name).replace(' ', '_') + '/' +
                                       "{0}_{1}_{2}_to_{3}.ID_Scores.tmp".format(self.blast_type, self.seq_record.name,
                                                                                 self.query_species,
                                                                                 self.target_species).replace(' ', '_'))

        recblast_output_unanno = Path("{0}_recblast_out".format(self.target_species).replace(' ', '_') + '/' +
                                      "{0}_{1}_tmp".format(self.blast_type,
                                                           self.seq_record.name).replace(' ', '_') + '/' +
                                      "unannotated_{0}_{1}.tmp".format(self.blast_type,
                                                                       self.seq_record.name).replace(' ', '_'))

        try:
            forward_blast_output.absolute().parent.mkdir(parents=True)
            if self.verbose > 1:
                with lock:
                    print('\t\tCreated directory \"{}\"!'.format(str(forward_blast_output.absolute().parent)))
        except FileExistsError:
            if self.verbose > 1:
                with lock:
                    print('\t\tDirectory \"{}\" already exists! Continuing!'.format(
                        str(forward_blast_output.absolute().parent)))
        try:
            forward_id_score_output.absolute().parent.mkdir(parents=True)
            if self.verbose > 1:
                with lock:
                    print('\t\tCreated directory \"{}\"!'.format(str(forward_id_score_output.absolute().parent)))
        except FileExistsError:
            if self.verbose > 1:
                with lock:
                    print('\t\tDirectory \"{}\" already exists! Continuing!'.format(
                        str(forward_blast_output.absolute().parent)))
        try:
            recblast_output_unanno.absolute().parent.mkdir(parents=True)
            if self.verbose > 1:
                with lock:
                    print('\t\tCreated directory \"{}\"!'.format(str(recblast_output_unanno.absolute().parent)))
        except FileExistsError:
            if self.verbose > 1:
                with lock:
                    print('\t\tDirectory \"{}\" already exists! Continuing!'.format(
                        str(forward_blast_output.absolute().parent)))

        if self.fw_blast_db == 'skip':
            if self.verbose:
                with lock:
                    print("\tSkipping Forward Blast!")
            pass
        else:
            if self.verbose:
                with lock:
                    print("\tPerforming forward BLAST for {}... ".format(self.seq_record.name), end='')
            blast(seq_record=self.seq_record, target_species=self.target_species, database=self.fw_blast_db,
                  query_species=self.query_species, filetype=self.infile_type, blast_type=self.blast_type,
                  local_blast=self.local_blast_1, expect=self.expect, megablast=self.megablast,
                  blastoutput_custom=str(forward_blast_output), perc_ident=self.perc_ident)
            if self.verbose:
                with lock:
                    print('Forward blast done!')
        with forward_blast_output.open("r") as forward_blasthits:
            if self.verbose:
                with lock:
                    print('\tOpening Forward blast output located at ', str(forward_blast_output.absolute()))
            blastrecord = NCBIXML.read(forward_blasthits)

        align_scorelist = []
        hsp_scorelist = []
        subject_range = []
        query_start_end = []
        if self.verbose:
            with lock:
                print('\tSorting through each alignment\'s HSPs to get top scores of all alignments...')
        for alignment in blastrecord.alignments:  # Todo: parallelize this using n_threads
            if self.verbose > 1:
                with lock:
                    print('\tAlignment: ', alignment.title)
            subject_range_hsp = []
            query_start_end_hsp = []
            for hsp in alignment.hsps:
                hsp_scorelist.append(hsp.score)
                subject_range_hsp.append(hsp.sbjct_start)
                subject_range_hsp.append(hsp.sbjct_end)
                query_start_end_hsp.append((hsp.query_start, hsp.query_end))
            hsp_scorelist.sort(reverse=True)
            query_start_end.append(i for i in merge_ranges(query_start_end_hsp))
            subject_range.append((subject_range_hsp[0], subject_range_hsp[-1]))
            if self.verbose > 1:
                with lock:
                    print("\tHSP Score List: \n\t\t", hsp_scorelist)
            align_scorelist.append(hsp_scorelist[0])
            if self.verbose > 1:
                with lock:
                    print("\tAlignment Score List: \n\t\t", align_scorelist)
        if self.verbose:
            with lock:
                print('\tDone with sorting!')

        with forward_id_score_output.open("w") as f_id_out:
            if self.verbose:
                with lock:
                    print('\tSearching through alignments to get top-scoring hit IDs...')
            has_written = False
            for align_index, alignment in enumerate(blastrecord.alignments):
                blast_got_hit = False  # Every time we consider a new alignment
                for hsp in alignment.hsps:
                    if blast_got_hit:
                        break
                    if ((hsp.score >= (self.perc_score * align_scorelist[align_index])) and
                            (hsp.expect <= self.expect) and
                            (sum([i[-1] - i[0] for i in query_start_end[align_index]]) / blastrecord.query_length
                                 >= self.perc_length)):
                        if self.verbose:
                            with lock:
                                print('\t\tFound annotation above threshold: ', alignment.title)
                        f_id_out.write('{0}\t{1}\t{2}\n'.format(alignment.title.replace('/t', ' '),
                                                                ':{0}-{1}'.format(subject_range[align_index][0],
                                                                                  subject_range[align_index][-1]),
                                                                hsp.score))
                        has_written = True
                        blast_got_hit = True
                    else:
                        continue
                if not blast_got_hit:
                    if self.verbose > 1:
                        with lock:
                            print('\t\tNOTE: FOR ALIGNMENT {}, NO HITS WERE FOUND!'.format(alignment.title))
            if not has_written:
                if self.verbose:
                    with lock:
                        Warning('WARNING! FOR SEQUENCE {}, NO HITS WERE FOUND! '
                                'CONTINUING TO NEXT SEQUENCE IN LIST!'.format(self.seq_record.name))
                return
        if self.verbose:
            with lock:
                print('Fetching sequences for ID\'ed hits...')
        try:  # TODO: WRITE FETCHSEQMP
            fetchseqMP(id_file=str(forward_id_score_output), species=target_species, email=email, source=fw_source,
                       output_type=output_type, output_name=str(recblast_output_unanno), db=fw_id_db, delim='\t',
                       id_type=id_type, batch_size=batch_size, passwd=passwd, version=fw_id_db_version, verbose=verbose)
            if verbose:
                print('Done with fetching!')
        except IndexError:
            print('WARNING! FETCHSEQ FAILED! SKIPPING THIS SEQUENCE!')
            continue
        # Little caveat: fetchseq by design appends a .[output_type] to the end of the file so we need to add that on:
        recblast_output_unanno = str(recblast_output_unanno) + '.{}'.format(output_type)
        # Now that we have the sequences we can do the Reverse BLAST:
        # Big caveat though: we need to do each target individually.







        return str(self.seq_record.name)

        # def run(self):



def recblastMP(seqfile, target_species, fw_blast_db='chromosome', infile_type='fasta', output_type='fasta',
               query_species='Homo sapiens', blast_type='blastn', local_blast_1=False, local_blast_2=False,
               rv_blast_db='nt', expect=10, perc_score=0.5, perc_ident=50, perc_length=0.5, megablast=True, email='',
               id_type='brute', fw_source='psql', fw_id_db='', fetch_batch_size=50, passwd='', fw_id_db_version='1.0',
               verbose='v', n_processes=10, n_threads=2):
    import multiprocessing
    import logging
    from pathlib import Path
    from Bio import SeqIO
    from Bio import __version__ as bp_version

    global_lock = multiprocessing.Lock()  # Stops threads from mixing output
    if isinstance(verbose, str):
        verbose = verbose.lower().count('v')
    elif isinstance(verbose, int) and verbose > 0:
        pass
    else:
        raise TypeError('Verbose must be either be an integer greater than or equal to zero, or a number of v\'s equal '
                        'to the desired level of verbosity')
    if verbose:
        print('BioPython version: ', bp_version)
        print('Beginning RecBlastMP!')
    if verbose == 1:
        print('Basic verbose mode active. Will print only essential commentary.')
    elif verbose == 2:
        print('Verbose mode was set to 2. Will elaborate considerably about the script.')
    elif verbose == 3:
        print('Debugging-level verbose mode set. You will be innunadated by text. Brace yourself, and hold on to your '
              'console.')
    elif (verbose > 10) and (verbose < 20):
        print('Listen, I only have so much to say. Clearly you want me to say a lot, and I get it. This world can be '
              'chaotic, and in times of coding need, you might be seeking a little more comfort. But I\'m just a '
              'script. There\'s only so much I can say about running Reciprocal-Best-Hit-Blasts. I can run quietly, '
              'I can tell you basics, I can even tell you debug-level stuff that will drive you crazy with code - but '
              'after that, I don\'t know what else to tell you, buddy. \n\n Anyways, now that that\'s out of the way,'
              'here\'s some verbose output:\n')
    elif verbose == 50:
        print("V FOR VERBOSE: \n"
              "\"Voilà! In view, a humble vaudevillian veteran cast vicariously as both victim and villain by the \n"
              "vicissitudes of Fate. This visage, no mere veneer of vanity, is a vestige of the vox populi, now \n"
              "vacant, vanished. However, this valourous visitation of a bygone vexation stands vivified and has \n"
              "vowed to vanquish these venal and virulent vermin vanguarding vice and vouchsafing the violently \n"
              "vicious and voracious violation of volition! The only verdict is vengeance; a vendetta held as a \n"
              "votive, not in vain, for the value and veracity of such shall one day vindicate the vigilant and \n"
              "the virtuous. \n"
              "Verily, this vichyssoise of verbiage veers most verbose, so let me simply add that it's my very good \n"
              "honour to meet you and you may call me [Reciprocal-Best-Hit-BLAST Script].\" \n"
              "\t - V \n"
              "Moore, Alan, David Lloyd, Steve Whitaker, and Siobhan Dodds. V for Vendetta. New York: DC Comics, 2005.")
    if verbose >= 3:
        multiprocessing.log_to_stderr(
            logging.DEBUG)  # Todo: See if you can make this output cleanly and uniformly, rather than all over the output.

    if verbose >= 2:
        print('Creating queues... ', end='')
    rb_queue = multiprocessing.JoinableQueue()
    rb_results = multiprocessing.Queue()
    if verbose >= 2:
        print('Done!')

    # Check Seqfile to make sure its real
    if verbose >= 1:
        print('Loading SeqFile records... ', end='')
    seqfile_path = Path(seqfile)

    try:
        rec_handle = SeqIO.parse(str(seqfile_path.absolute()), output_type)
        if verbose >= 1:
            print('Done!')
    except FileNotFoundError:
        raise
    if verbose >= 1:
        print('Creating RecBlast Threads... ')
    rec_blast_instances = [RecBlastMP_Thread(proc_id=str(i + 1), rb_queue=rb_queue, rb_results_queue=rb_results,
                                             lock=global_lock) for i in range(n_processes)]
    for rcb in rec_blast_instances:
        rcb.start()
    for rec in [i for i in rec_handle]:
        rb_queue.put(RecBlast(seq_record=rec, target_species=target_species, fw_blast_db=fw_blast_db,
                              infile_type=infile_type, output_type=output_type, query_species=query_species,
                              blast_type=blast_type, local_blast_1=local_blast_1, local_blast_2=local_blast_2,
                              rv_blast_db=rv_blast_db, expect=expect, perc_score=perc_score, perc_ident=perc_ident,
                              perc_length=perc_length, megablast=megablast, email=email, id_type=id_type,
                              fw_source=fw_source, fw_id_db=fw_id_db, fetch_batch_size=fetch_batch_size, passwd=passwd,
                              fw_id_db_version=fw_id_db_version, verbose=verbose, n_threads=2))
    for i in range(n_processes):
        rb_queue.put(None)

    # Todo: figure out output.
    recblast_out = list()
    while n_processes:
        recblast_out.append(rb_results.get())
        n_processes -= 1
    return recblast_out


"""
    pool = mp.Pool(n_threads)

    #for seq_batch_gen in n_threads:
    try:
        pool.map_async(partial(recblast, target_species=target_species, fw_blast_db=fw_blast_db,
                                   infile_type=infile_type, output_type=output_type, query_species=query_species,
                                   blast_type=blast_type, localblast1=localblast1, localblast2=localblast2,
                                   rv_blast_db=rv_blast_db, expect=expect, scoreperc=scoreperc,
                                   perc_ident=perc_ident, perc_length=perc_length, megablast=megablast, email=email,
                                   id_type=id_type, fw_source=fw_source, fw_id_db=fw_id_db, batch_size=batch_size,
                                   passwd=passwd, fw_id_db_version=fw_id_db, verbose=verbose, parallel = True),
                       seq_batch_gen)
    except KeyboardInterrupt:
        sys.stdout.write('\033[0m')
        sys.stdout.write('User Interupt\n')
    pool.close()
    pool.join()
"""
