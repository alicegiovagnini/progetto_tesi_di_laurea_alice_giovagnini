from sqlalchemy import create_engine, Column, Integer, Float, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import sqlite3

# SQLalchemy setup
Base = declarative_base()

class UserResults(Base):  
    __tablename__ = 'user_results'
    id = Column(Integer, primary_key=True, autoincrement=True)
    initial_correlation = Column(Float, nullable=True)
    final_correlation = Column(Float, nullable=False)
    improvement = Column(Float, nullable=False)
    #weight_of_advice = Column(Float, nullable=True)
    username = Column(String,nullable = True)
    partner = Column(String, nullable=True)
    in_accordo = Column(String,nullable = False)

    
class UserResultsAlone(Base): #nel caso di un test individuale
    __tablename__ = 'risultati'
    id = Column(Integer, primary_key=True, autoincrement=True)
    initial_correlation = Column(Float, nullable=True)
    final_correlation = Column(Float, nullable=False)
    improvement = Column(Float, nullable=False)
    modalita = Column(String,nullable= False)
    
class UserInfo(Base):
    __tablename__ = 'user_info'
    id = Column(Integer, primary_key=True, autoincrement=True)
    età = Column(Integer , nullable = False)
    sesso = Column(String, nullable = False)
    professione = Column(String, nullable = True)
    esperienza_llm = Column(String, nullable = False)
    
    
class UserQuestions(Base):
    __tablename__ = 'user_questions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    question_columns = {f'question_{i}': Column(Integer, nullable=False) for i in range(1, 22)}
    locals().update(question_columns)

class UserPostQuestionnaire(Base):
    __tablename__ = 'user_post_questionnaire'
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_question_columns = {f'post_question_{i}': Column(Integer, nullable=False) for i in range(1, 11)}
    locals().update(post_question_columns)
    
    
    
# funzioni per connettersi al database e creare le tabelle---------------------------------------
def get_engine(db_url='sqlite:///prova2.db'):
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return engine

def get_engine_alone(db_url='sqlite:///alone.db'):
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()



def insert_user_results_to_db(session, initial_correlation, final_correlation, improvement,username,partner,in_accordo, average_feedback=None):
    if(username == ""):
        username = None
    if(partner == ""):
        partner = None
        
    user_result = UserResults(
        initial_correlation=initial_correlation,
        final_correlation=final_correlation,
        improvement=improvement,
        
        username = username,
        partner = partner,
        in_accordo = in_accordo,

    )
    session.add(user_result)
    session.commit()
    
        
def insert_user_info_to_db(session, sesso, età , professione, esperienza):
    user_info = UserInfo(
        età = età,
        sesso = sesso,
        professione = professione,
        esperienza_llm = esperienza
    )
    session.add(user_info)
    session.commit()


def insert_user_questions_to_db(session, risposte_questionario):

    user_questions = UserQuestions(
        **{f'question_{i}': risposte_questionario[i] for i in range(1, 22)}
    )
    session.add(user_questions)
    session.commit()
    
    
def insert_user_results_alone(session, initial_correlation, final_correlation, improvement,modalita):
       
    user_result = UserResultsAlone(
        initial_correlation=initial_correlation,
        final_correlation=final_correlation,
        improvement=improvement,
        modalita= modalita,
    )
    session.add(user_result)
    session.commit()

def insert_user_post_questions_to_db(session, risposte_post_questionario):
    user_post_questions = UserPostQuestionnaire(
        **{f'post_question_{i}': risposte_post_questionario[i] for i in range(1, 11)}
    )
    session.add(user_post_questions)
    session.commit()