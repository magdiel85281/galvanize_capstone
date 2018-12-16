import pandas as pd
from pymongo import MongoClient

from nltk.tokenize import word_tokenize, wordpunct_tokenize, RegexpTokenizer
from nltk.stem.snowball import SnowballStemmer
from nltk.stem.wordnet  import WordNetLemmatizer
from nltk.corpus import stopwords
from nltk.util import ngrams, skipgrams
import string
import re


def get_data():
    '''
    Query data from mongo db bills.bill_details and return a pandas dataframe.
    
    The data relevant to this project is currently set up to be limited to the 
    110th Congress forward.
    --------------------
    Parameters: None.
    --------------------    
    Returns: pandas dataframe with relevant data and corresponding labels.
                
    '''
    # connect to mongodb
    client = MongoClient() # defaults to localhost
    db = client.bills
    bill_details = db.bill_details
    
    # get mongoo data and convert mongo query resuls to dataframe
    # need to execute query (.find) everytime i refer to it?
    records_with_text = bill_details.find({'body': {'$regex': 'e'}})
    data = pd.DataFrame(list(records_with_text))

    # filter out simple resolutions, concurrent resolutions, and amendments (for prelim model)
    data = data[(data['leg_type'] != 'RESOLUTION') & (data['leg_type'] != 'CONCURRENT RESOLUTION') & (data['leg_type'] != 'AMENDMENT')]

    print('------------------')
    print('Creating labels in column \'passed\'...')
    
    # break up dataframe into those that became law and others (did not or still pending)
    became_law = data[(data['bill_status'] == 'Became Law') | (data['bill_status'] == 'Became Private Law')]
    others = data[(data['bill_status'] != 'Became Law') & (data['bill_status'] != 'Became Private Law')]

    became_law.loc[:, 'passed'] = 1



    # break up others into current congress and previous ones. Anything that hasn't been signed into law
    # before current session is dead. Currently, all bills vetoed by the president come from previous congresses
    current_cong = others[others['congress_id'] == '115th']
    prev_cong = others[others['congress_id'] != '115th']

    prev_cong.loc[:, 'passed'] = 0



    # let's label To President and Resolving Differences with 1. Everything else is on the floor
    to_pres = current_cong[(current_cong['bill_status'] == 'To President') | (current_cong['bill_status'] == 'Resolving Differences')]
    on_floor = current_cong[(current_cong['bill_status'] != 'To President') & (current_cong['bill_status'] != 'Resolving Differences')]

    to_pres.loc[:, 'passed'] = 1



    # break up bills on the floor to failed (0) and not failed
    failed = on_floor[on_floor['bill_status'].str.startswith('Failed')]
    not_failed = on_floor[~on_floor['bill_status'].str.startswith('Failed')]

    failed.loc[:, 'passed'] = 0



    # bills that haven't failed yet have either been just introduced or on their way
    # label introduced with 'in_progress'. These will not be a part of our model.
    introduced = not_failed[not_failed['bill_status'] == 'Introduced']
    beyond_intro = not_failed[not_failed['bill_status'] != 'Introduced']

    introduced.loc[:, 'passed'] = 'in_progress'



    # there are bills that started in one chamber and have already passed the other. We'll label
    # these with a 1
    passed_opp_chamber = beyond_intro[(beyond_intro['bill_status'] == 'Passed House') & (beyond_intro['leg_id'].str.startswith('S')) | 
                              (beyond_intro['bill_status'] == 'Passed Senate') & (beyond_intro['leg_id'].str.startswith('H'))]

    passed_opp_chamber.loc[:, 'passed'] = 1



    # bills that are still in the chamber they were introduced in are 'in_progress'
    in_orig_chamber = beyond_intro[(beyond_intro['bill_status'] == 'Passed House') & (beyond_intro['leg_id'].str.startswith('H')) | 
                              (beyond_intro['bill_status'] == 'Passed Senate') & (beyond_intro['leg_id'].str.startswith('S'))]    

    in_orig_chamber.loc[:, 'passed'] = 'in_progress'



    # bring all the information back together
    data_l = pd.concat([became_law, prev_cong, to_pres, failed, introduced, passed_opp_chamber, in_orig_chamber])

    # filter out those that are still in progress
    df = data_l[data_l['passed'] != 'in_progress']

    # filter for most recent congress_ids
    small_df = df[(df['congress_id'] == '115th') | 
              (df['congress_id'] == '114th') | 
              (df['congress_id'] == '113th')| 
              (df['congress_id'] == '112th')| 
              (df['congress_id'] == '111th')| 
              (df['congress_id'] == '110th')]
    
    print('------------------')
    print('------------------')
    print('Data is from the 110th Congress (2007) to present')
    print('------------------')
    
    return small_df



def process_corpus(df, corpus_col_name, label_col_name):
    '''
    Processes the text in df[corpus_col_name] to return a corpus (list) and the series of 
    corresponding labels in df[label_col_name].
    
    The intent of this function is to feed the output into a stratified train-test split.
    -------------------
    Parameters: df - pandas dataframe
                col_name - name of column in df that contains the text to be processed.
    -------------------
    Returns: X - a list of documents
             y - a pandas series of corresponding labels
    '''
    # create a corpus
    print('------------------')
    print('Creating corpus...')
    documents = list(df[corpus_col_name])

    # remove numbers
    documents = list(map(lambda x: ' '.join(re.split('[,_\d]+', x)), documents))

    # tokenize the corpus
    print('------------------')
    print('Tokenizing...')
    corpus = [word_tokenize(content.lower()) for content in documents]

    # strip out the stop words from each 
    print('------------------')
    print('Stripping out stop words, punctuation, and numbers...')
    stop_words = stopwords.words('english')
    stop_words.extend(['mr', 'ms', 'mrs', 'said', 'year', 'would', 'could', 'also', 'shall', '_______________________________________________________________________'])
    # print(stop_words)
    corpus = [[token for token in doc if token not in stop_words] for doc in corpus]
    # corpus[0]

    # strip out the punctuation
    punc = set(string.punctuation)
    # print(punc)
    corpus = [[token for token in doc if token not in punc] for doc in corpus]
    # corpus[0]

    # strip out the punctuation
    string.digits


    # lemmatize (and maybe stem?)
    print('------------------')
    print('Lemmatizing...')
    lemmer = WordNetLemmatizer()
    corpus = [[lemmer.lemmatize(word) for word in doc] for doc in corpus]
    # corpus[0]

    # build a vocabulary
    print('------------------')
    print('Creating a vocabulary...')
    vocab_set = set()
    [[vocab_set.add(token) for token in tokens] for tokens in corpus]
    vocab = list(vocab_set)
    # vocab[100000:100020]

    # # for later model...
    # # examine n-grams...
    # # bigrams (two words side-by-side)
    # print('------------------')
    # print('Creating lists of bigrams, trigrams, skipgrams, etc...')
    # bigrams = [list(ngrams(sequence = doc, n = 2)) for doc in corpus]
    # trigrams = [list(ngrams(sequence = doc, n = 3)) for doc in corpus]
    # #... more?

    # # skipgrams (n-grams that skip k words)
    # skipgrams = [list(skipgrams(sequence = doc, n = 2, k = 1)) for doc in corpus]


    # rejoin each doc in corpus so each doc is a single string
    corpus = [' '.join(tokens) for tokens in corpus]

    print('------------------')
    print('NLP preprocessing complete ...')

    print('------------------')
    print('Creating train-test split and vectorizing ...')
    X = corpus
    y = df[labels_col_name].astype('int')
    
    return X, y