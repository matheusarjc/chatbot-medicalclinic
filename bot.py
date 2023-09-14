import os
from dotenv import load_dotenv
import telebot
from telebot import types
from datetime import datetime, timedelta
import sqlite3

load_dotenv()
BOT_TOKEN = os.environ.get('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

user_states = {}
scheduled_appointments = {}
user_data ={}


# Função para exibir o menu de opções
def show_menu(chat_id):
    if 'menu_shown' in user_states and user_states['menu_shown']:
        greeting = "Selecione uma opção no menu:"
    else:
        greeting = "Olá, seja bem-vindo à Clínica Médica! Como posso ajudar você?"
        user_states['menu_shown'] = True  # Marca que o menu já foi mostrado

    markup = types.ReplyKeyboardMarkup(row_width=2)
    btn1 = types.KeyboardButton("Primeira consulta")
    btn2 = types.KeyboardButton("Agendar uma consulta")
    btn3 = types.KeyboardButton("Revisão")
    btn4 = types.KeyboardButton("Remarcar")
    btn5 = types.KeyboardButton("Falar com atendente")
    markup.add(btn1, btn2, btn3, btn4, btn5)

    bot.send_message(chat_id, greeting, reply_markup=markup)


# Comando /start para iniciar a interação e exibir o menu
@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    user_states[chat_id] = 'menu'
    show_menu(chat_id)


# Lida com as opções do menu
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'menu')
def handle_menu_options(message):
    chat_id = message.chat.id
    user_choice = message.text
    match user_choice:
        case "Primeira consulta":
            user_states[chat_id] = 'primeira_consulta'
            bot.send_message(chat_id, "Por favor, informe seu nome completo:")
        case "Agendar uma consulta":
            user_states[chat_id] = 'check_rg'
            bot.send_message(chat_id, "Por favor, insira seu RG:")
        case "Revisão":
            user_states[chat_id] = 'check_rg_revisao'
            bot.send_message(chat_id, "Por favor, insira seu RG:")


# PRIMEIRA CONSULTA

# Lida com a etapa de coletar o nome completo
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'primeira_consulta')
def collect_birth_date(message):
    chat_id = message.chat.id
    user_states[chat_id] = 'data_nascimento'
    user_data[chat_id] = {'nome_completo': message.text}
    bot.send_message(chat_id, "Ótimo, agora informe sua data de nascimento (DD-MM-AAAA):")


@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'data_nascimento')
def collect_rg(message):
    chat_id = message.chat.id
    user_states[chat_id] = 'rg'
    user_data[chat_id]['data_nascimento'] = message.text  # Adicionado aqui
    bot.send_message(chat_id, "Certo, agora informe o seu RG:")


@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'rg')
def collect_insurance(message):
    chat_id = message.chat.id
    user_states[chat_id] = 'convenio'

    # Inicializa um subdicionário para o chat_id, se ainda não existir
    if chat_id not in user_data:
        user_data[chat_id] = {}

    user_data[chat_id]['rg'] = message.text  # Armazena o RG no subdicionário
    bot.send_message(chat_id, "Último passo, escolha seu convênio:")
    markup = types.ReplyKeyboardMarkup(row_width=2)
    btn1 = types.KeyboardButton("Plano de saúde")
    btn2 = types.KeyboardButton("Particular")
    markup.add(btn1, btn2)
    bot.send_message(chat_id, "Escolha uma opção:", reply_markup=markup)


@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'convenio')
def collect_appointment(message):
    chat_id = message.chat.id
    user_states[chat_id] = 'appointment'
    user_data[chat_id]['convenio'] = message.text

    # Insere os dados do paciente na tabela
    with sqlite3.connect('clinic_database.db') as conn:
        insert_query = '''
            INSERT INTO patients (chat_id, nome_completo, data_nascimento, rg, convenio)
            VALUES (?, ?, ?, ?, ?);
            '''
        data = (chat_id, user_data[chat_id]['nome_completo'], user_data[chat_id]['data_nascimento'],
                user_data[chat_id]['rg'], user_data[chat_id]['convenio'])
        conn.execute(insert_query, data)
        conn.commit()

    bot.send_message(chat_id,
                     "Informações coletadas! Obrigado por se cadastrar. Agora agende a sua consulta! Escolha o dia e "
                     "horário disponível:")
    show_available_appointments(chat_id)


# AGENDAR UMA CONSULTA
# Verificar RG e agendar consulta
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'check_rg')
def check_rg_and_schedule(message):
    chat_id = message.chat.id
    rg = message.text
    current_date = datetime.now().date()

    with sqlite3.connect('clinic_database.db') as conn:
        cursor = conn.execute("SELECT * FROM patients WHERE rg = ?", (rg,))
        patient_data = cursor.fetchone()

        if patient_data:
            # Verifica se já tem consulta marcada para o dia
            cursor = conn.execute("SELECT * FROM patients WHERE rg = ? AND data_agendamento = ?", (rg, current_date))
            appointment_data = cursor.fetchone()

            if appointment_data:
                bot.send_message(chat_id, "Você já tem uma consulta marcada para hoje. Escolha outro dia.")
            else:
                # Verifica se o dia da consulta já passou
                cursor = conn.execute("SELECT * FROM patients WHERE rg = ?", (rg,))
                last_appointment_data = cursor.fetchone()
                last_appointment_date = datetime.strptime(last_appointment_data[6], "%Y-%m-%d").date()

                if last_appointment_date < current_date:
                    # Atualiza a coluna "ultima_consulta"
                    conn.execute("UPDATE patients SET ultima_consulta = ? WHERE rg = ?", (last_appointment_date, rg))
                    conn.commit()

                user_states[chat_id] = 'appointment'
                bot.send_message(chat_id, "Você pode agendar uma nova consulta.")
                show_available_appointments(chat_id)
        else:
            bot.send_message(chat_id, "RG não encontrado. Por favor, realize o cadastro primeiro.")
            user_states[chat_id] = 'menu'  # Redefine o estado para 'menu'
            show_menu(chat_id)  # Mostra o menu de opções novamente


# Horários de trabalho
working_days = ['Tuesday', 'Thursday']
start_time = datetime.strptime("08:00", "%H:%M")
end_time = datetime.strptime("18:00", "%H:%M")
lunch_start = datetime.strptime("12:00", "%H:%M")
lunch_end = datetime.strptime("13:00", "%H:%M")
appointment_duration = timedelta(hours=1)


# Função para calcular os horários disponíveis para consulta
def calculate_available_appointments():
    available_appointments = {}
    current_date = datetime.now().date()

    while current_date.weekday() < 5:  # Considerando somente os dias úteis
        weekday = current_date.strftime("%A")
        if weekday in working_days:
            available_times = []
            current_time = start_time

            while current_time + appointment_duration <= end_time:
                if current_time < lunch_start or current_time >= lunch_end:
                    available_times.append(current_time.strftime("%H:%M"))
                current_time += appointment_duration

            available_appointments[current_date.strftime("%Y-%m-%d")] = available_times

        current_date += timedelta(days=1)

    return available_appointments


# Função para exibir as opções de datas e horários disponíveis
def show_available_appointments(chat_id):
    available_appointments = calculate_available_appointments()

    markup = types.ReplyKeyboardMarkup(row_width=2)
    for date, times in available_appointments.items():
        date_button = types.KeyboardButton(date)
        markup.add(date_button)

    bot.send_message(chat_id, "Escolha a data para agendar sua consulta:", reply_markup=markup)


# Escolher data
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'appointment')
def handle_appointment_time(message):
    chat_id = message.chat.id
    user_states[chat_id] = 'appointment_time'
    chosen_date = message.text
    available_times = calculate_available_appointments()[chosen_date]
    if available_times:
        markup = types.ReplyKeyboardMarkup(row_width=2)
        for time in available_times:
            time_button = types.KeyboardButton(time)
            markup.add(time_button)

        bot.send_message(chat_id, "Escolha o horário para agendar sua consulta:", reply_markup=markup)
    else:
        bot.send_message(chat_id,
                         "Desculpe, não há horários disponíveis para essa data. Por favor, escolha outra data.")


# Cria uma conexão com o banco de dados (ou cria um novo se não existir)
conn = sqlite3.connect('clinic_database.db')

# Cria a tabela para armazenar os dados dos pacientes
create_table_query = '''
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    nome_completo TEXT,
    data_nascimento TEXT,
    rg TEXT,
    convenio TEXT,
    data_agendamento TEXT,
    horario_agendamento TEXT,
    ultima_consulta TEXT,
    nova_consulta TEXT
);
'''
conn.execute(create_table_query)
conn.commit()

try:
    conn.execute("ALTER TABLE patients ADD COLUMN revisao_assunto TEXT;")
    conn.commit()
except sqlite3.OperationalError as e:
    if "duplicate column name" in str(e):
        print("A coluna 'revisao_assunto' já existe.")
    else:
        print("Erro ao adicionar a coluna:", e)


# Escolher horário
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'appointment_time')
def handle_appointment_available(message):
    chat_id = message.chat.id
    chosen_time = message.text
    available_appointments = calculate_available_appointments()

    # Encontra a data correspondente ao horário escolhido
    chosen_date = [date for date, times in available_appointments.items() if chosen_time in times][0]

    with sqlite3.connect('clinic_database.db') as conn:
        cursor = conn.execute("SELECT * FROM patients WHERE chat_id = ?", (chat_id,))
        patient_data = cursor.fetchone()

        if patient_data:
            if patient_data[6] and patient_data[7]:  # Verifica se "data_agendamento" e "horario_agendamento" não são None
                last_appointment_datetime = datetime.strptime(f"{patient_data[6]} {patient_data[7]}", "%Y-%m-%d %H:%M")
                current_datetime = datetime.now()

                if last_appointment_datetime < current_datetime:
                    conn.execute("UPDATE patients SET ultima_consulta = ? WHERE chat_id = ?", (patient_data[6], chat_id))
                    conn.commit()

            if patient_data[8]:  # Verifica se "ultima_consulta" está preenchida
                conn.execute("UPDATE patients SET nova_consulta = ? WHERE chat_id = ?", (chosen_date, chat_id))
            else:
                conn.execute("UPDATE patients SET data_agendamento = ?, horario_agendamento = ? WHERE chat_id = ?", (chosen_date, chosen_time, chat_id))

            conn.commit()

    bot.send_message(chat_id, f"Consulta agendada para {chosen_date} às {chosen_time}. Obrigado!")


# REVISÃO
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'check_rg_revisao')
def check_rg_and_show_revision_options(message):
    chat_id = message.chat.id
    rg = message.text

    with sqlite3.connect('clinic_database.db') as conn:
        cursor = conn.execute("SELECT * FROM patients WHERE rg = ?", (rg,))
        patient_data = cursor.fetchone()

        if patient_data:
            user_states[chat_id] = 'revisao_assunto'
            markup = types.ReplyKeyboardMarkup(row_width=2)
            btn1 = types.KeyboardButton("Pós cirurgia")
            btn2 = types.KeyboardButton("Resultados")
            markup.add(btn1, btn2)
            bot.send_message(chat_id, "Escolha o assunto da revisão:", reply_markup=markup)
        else:
            bot.send_message(chat_id, "RG não encontrado. Por favor, realize o cadastro primeiro.")
            user_states[chat_id] = 'menu'
            show_menu(chat_id)

# Atualizar o banco de dados e mostrar as datas disponíveis
@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == 'revisao_assunto')
def handle_revision_subject(message):
    chat_id = message.chat.id
    revisao_assunto = message.text

    with sqlite3.connect('clinic_database.db') as conn:
        conn.execute("UPDATE patients SET revisao_assunto = ? WHERE chat_id = ?", (revisao_assunto, chat_id))
        conn.commit()

    user_states[chat_id] = 'appointment'
    bot.send_message(chat_id, "Assunto da revisão registrado. Agora escolha a data e o horário para a revisão.")
    show_available_appointments(chat_id)

# Inicia o bot
bot.polling()
