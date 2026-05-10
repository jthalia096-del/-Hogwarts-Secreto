import asyncio
import sqlite3
import re
import unicodedata
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, BotCommand
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

TOKEN = "8454290204:AAH-C-H-Wt0WMVJU7KjqCmNsocsNX3hv-Xo"
ADMINS = [8672397104]  # coloque seu ID aqui
GRUPO_ID = -1003640277537  # coloque o ID do grupo aqui

bot = Bot(TOKEN)
dp = Dispatcher()

conn = sqlite3.connect("pedidos.db", check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA temp_store=MEMORY")
conn.execute("PRAGMA cache_size=-64000")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS pedidos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    nome TEXT,
    username TEXT,
    pedido TEXT,
    status TEXT,
    grupo_msg_id INTEGER,
    arquivo_id TEXT,
    arquivo_tipo TEXT,
    figurinha_id TEXT,
    chave_livro TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS config (
    chave TEXT,
    valor TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS entregues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chave_livro TEXT UNIQUE,
    nome_livro TEXT,
    pedido_id INTEGER,
    arquivo_id TEXT,
    data_registro TEXT DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

pedido_selecionado = {}
arquivos_pendentes = {}
modo_edicao = {}


def autorizado(user_id: int):
    return user_id in ADMINS


def pegar_config(chave):
    cursor.execute(
        "SELECT valor FROM config WHERE chave = ? ORDER BY rowid DESC LIMIT 1",
        (chave,)
    )
    resultado = cursor.fetchone()
    return resultado[0] if resultado else ""


def salvar_config(chave, valor):
    cursor.execute("SELECT rowid FROM config WHERE chave = ?", (chave,))
    existe = cursor.fetchone()

    if existe:
        cursor.execute(
            "UPDATE config SET valor = ? WHERE chave = ?",
            (valor, chave)
        )
    else:
        cursor.execute(
            "INSERT INTO config (chave, valor) VALUES (?, ?)",
            (chave, valor)
        )

    conn.commit()


configs_padrao = {
    "msg_pedido": "📜 Pergaminho registrado em Hogwarts.\n\nOs professores da biblioteca já iniciaram as buscas. 📚✨",
    "msg_arquivo": "🦉📚 Grimório localizado.\nA coruja já encaminhou o exemplar aos Arquivos de Hogwarts. ✨📜",
    "msg_nao_encontrei": "🔎 Este pergaminho ainda não foi localizado no acervo.\nEle ficará guardado nos Pergaminhos Não Localizados.",
    "msg_ja_postado": "🧠📚 Este grimório já repousa no Acervo de Hogwarts.\n\nConsulte os Arquivos de Hogwarts para localizar o pergaminho solicitado. ✨📜"
}

for chave, valor in configs_padrao.items():
    if not pegar_config(chave):
        salvar_config(chave, valor)


def remover_acentos(texto):
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto


def extrair_nome_livro(texto):
    linhas = texto.splitlines()
    campos_validos = (
        "livro:",
        "nome:",
        "nome do livro:",
        "grimório:",
        "grimorio:",
        "grimório/livros solicitado:",
        "grimorio/livros solicitado:",
        "grimório/livro solicitado:",
        "grimorio/livro solicitado:",
        "grimório solicitado:",
        "grimorio solicitado:",
    )

    for i, linha in enumerate(linhas):
        linha_limpa = linha.strip()
        linha_lower = linha_limpa.lower()

        for campo in campos_validos:
            if linha_lower.startswith(campo):
                valor = linha_limpa.split(":", 1)[1].strip() if ":" in linha_limpa else ""
                if valor:
                    return valor
                if i + 1 < len(linhas):
                    proxima = linhas[i + 1].strip()
                    if proxima:
                        return proxima

    return texto[:80].strip()


def criar_chave_livro(texto):
    nome = extrair_nome_livro(texto)
    nome = remover_acentos(nome.lower())
    nome = re.sub(r"[^a-z0-9]+", " ", nome)
    nome = re.sub(r"\s+", " ", nome).strip()
    return nome


def formatar_mensagem_config(chave, **dados):
    texto = pegar_config(chave)
    try:
        return texto.format(**dados)
    except Exception:
        return texto


def parece_ficha(texto: str):
    texto = (texto or "").lower()
    return (
        "pergaminho de solicitação" in texto
        or "pergaminho de solicitacao" in texto
        or "#pedido" in texto
        or "livro:" in texto
        or "nome do livro:" in texto
        or "grimório/livros solicitado" in texto
        or "grimorio/livros solicitado" in texto
        or "grimório:" in texto
        or "grimorio:" in texto
    )


def numero_visual(pedido_id, status):
    cursor.execute("""
    SELECT id FROM pedidos
    WHERE status = ?
    ORDER BY id ASC
    """, (status,))

    ids = [linha[0] for linha in cursor.fetchall()]

    if pedido_id in ids:
        return ids.index(pedido_id) + 1

    return pedido_id


def contadores_texto():
    cursor.execute("SELECT COUNT(*) FROM entregues")
    total_acervo = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE status = 'pendente'")
    total_missoes = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE status = 'nao_encontrado'")
    total_nao_encontradas = cursor.fetchone()[0]

    return (
        "📊 Registro da Biblioteca\n\n"
        f"📚 Pergaminhos entregues ao acervo: {total_acervo}\n"
        f"📜 Pergaminhos aguardando: {total_missoes}\n"
        f"🔎 Pergaminhos não localizados: {total_nao_encontradas}"
    )


def menu_pv():
    kb = InlineKeyboardBuilder()
    kb.button(text="📜 Pergaminhos registrados", callback_data="missoes")
    kb.button(text="🔎 Pergaminhos Não Localizados", callback_data="missoes_nao_encontradas")
    kb.button(text="📊 Registro da Biblioteca", callback_data="contadores")
    kb.button(text="✏️ Personalizar Mensagens", callback_data="personalizar")
    kb.button(text="🧠 Arquivo Inteligente", callback_data="arquivo_inteligente")
    kb.button(text="🧹 Limpar pergaminhos concluídos", callback_data="limpar")
    kb.adjust(1)
    return kb.as_markup()


def menu_personalizar():
    kb = InlineKeyboardBuilder()
    kb.button(text="📜 Mensagem do pergaminho", callback_data="editar_msg_pedido")
    kb.button(text="🎯 Mensagem do arquivo", callback_data="editar_msg_arquivo")
    kb.button(text="🔎 Mensagem: não encontrei", callback_data="editar_msg_nao_encontrei")
    kb.button(text="🖼️ Figurinha: não encontrei", callback_data="editar_sticker_nao_encontrei")
    kb.button(text="⬅️ Voltar", callback_data="voltar_menu")
    kb.adjust(1)
    return kb.as_markup()


def menu_arquivo_inteligente():
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Mensagem: já está no acervo", callback_data="editar_msg_ja_postado")
    kb.button(text="📊 Ver contadores", callback_data="contadores")
    kb.button(text="⬅️ Voltar", callback_data="voltar_menu")
    kb.adjust(1)
    return kb.as_markup()


def menu_pedidos(pedidos):
    kb = InlineKeyboardBuilder()

    for indice, pedido in enumerate(pedidos, start=1):
        pedido_id, nome = pedido
        kb.button(
            text=f"📜 Pergaminho {indice} - {nome}",
            callback_data=f"selecionar_{pedido_id}"
        )

    kb.adjust(1)
    return kb.as_markup()


def menu_missao_acoes(pedido_id):
    kb = InlineKeyboardBuilder()
    kb.button(text="🧠 Já está no acervo", callback_data=f"ja_acervo_{pedido_id}")
    kb.button(text="🔎 Não localizei o grimório", callback_data=f"nao_encontrei_{pedido_id}")
    kb.button(text="❌ Cancelar envio do pergaminho", callback_data=f"cancelar_envio_{pedido_id}")
    kb.button(text="✅ Arquivar pergaminho", callback_data=f"finalizar_{pedido_id}")
    kb.button(text="⬅️ Voltar aos pergaminhos", callback_data="missoes")
    kb.adjust(1)
    return kb.as_markup()


@dp.message(Command("start"))
async def start(message: Message):
    if message.chat.type != "private":
        return

    if not autorizado(message.from_user.id):
        await message.answer("⛔ Apenas guardiões autorizados podem usar este bot.")
        return

    await message.answer(
        "📚 Bem-vinda, Guardiã dos Livros.\n\n"
        "Escolha uma opção:",
        reply_markup=menu_pv()
    )


@dp.message(Command("menu"))
async def menu(message: Message):
    if message.chat.type != "private":
        return

    if not autorizado(message.from_user.id):
        return

    await message.answer(
        "📚 Menu dos Arquivos de Hogwarts:",
        reply_markup=menu_pv()
    )


@dp.message(F.chat.type == "private", F.text)
async def receber_texto_personalizado(message: Message):
    if not autorizado(message.from_user.id):
        return

    chave = modo_edicao.get(message.from_user.id)

    if not chave:
        return

    if chave == "sticker_nao_encontrei":
        await message.answer("⚠️ Envie uma figurinha, não uma mensagem de texto.")
        return

    salvar_config(chave, message.text)
    modo_edicao.pop(message.from_user.id, None)

    nova = pegar_config(chave)

    await message.answer(
        "✅ Mensagem personalizada salva com sucesso!\n\n"
        "📌 Nova mensagem salva:\n\n"
        f"{nova}",
        reply_markup=menu_pv()
    )


@dp.message(F.chat.id == GRUPO_ID, F.text)
async def registrar_pedido(message: Message):
    texto = message.text

    if not parece_ficha(texto):
        return

    user = message.from_user
    nome = user.full_name
    username = user.username or "sem username"

    chave_livro = criar_chave_livro(texto)
    nome_livro = extrair_nome_livro(texto)

    cursor.execute("""
    INSERT INTO pedidos
    (user_id, nome, username, pedido, status, grupo_msg_id, chave_livro)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user.id,
        nome,
        username,
        texto,
        "pendente",
        message.message_id,
        chave_livro
    ))
    conn.commit()

    await message.reply(pegar_config("msg_pedido"))


@dp.callback_query(F.data == "missoes")
async def missoes(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    cursor.execute("""
    SELECT id, nome
    FROM pedidos
    WHERE status = 'pendente'
    ORDER BY id ASC
    """)
    pedidos = cursor.fetchall()

    if not pedidos:
        await callback.message.answer(
            "✅ Não há pergaminhos registrados no momento.",
            reply_markup=menu_pv()
        )
        return

    await callback.message.answer(
        "📜 Escolha qual pergaminho deseja abrir:",
        reply_markup=menu_pedidos(pedidos)
    )


@dp.callback_query(F.data == "missoes_nao_encontradas")
async def missoes_nao_encontradas(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    cursor.execute("""
    SELECT id, nome
    FROM pedidos
    WHERE status = 'nao_encontrado'
    ORDER BY id ASC
    """)
    pedidos = cursor.fetchall()

    if not pedidos:
        await callback.message.answer(
            "✅ Não há pergaminhos não localizados no momento.",
            reply_markup=menu_pv()
        )
        return

    await callback.message.answer(
        "🔎 Pergaminhos guardados como não localizados:",
        reply_markup=menu_pedidos(pedidos)
    )


@dp.callback_query(F.data.startswith("selecionar_"))
async def selecionar_pedido(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    pedido_id = int(callback.data.replace("selecionar_", ""))

    cursor.execute("""
    SELECT id, nome, pedido, status
    FROM pedidos
    WHERE id = ? AND status IN ('pendente', 'nao_encontrado')
    """, (pedido_id,))
    pedido = cursor.fetchone()

    if not pedido:
        await callback.message.answer("⚠️ Esse pergaminho não está mais disponível.")
        return

    id_pedido, nome, pedido_texto, status = pedido
    numero = numero_visual(id_pedido, status)

    pedido_selecionado[callback.from_user.id] = pedido_id
    arquivos_pendentes[callback.from_user.id] = []

    await callback.message.answer(
        f"🕯️✨ DIRETORA RAVENNA BLACK\n\n"
        f"🦉 Pergaminho {numero} selecionado\n\n"
        f"👤 Aluno: {nome}\n\n"
        f"{pedido_texto}\n\n"
        "📦 Envie os grimórios no PV.\n"
        "🦉 Após concluir, envie a figurinha de confirmação.\n\n"
        "✅ O pergaminho só sai da lista quando você tocar em Arquivar pergaminho.",
        reply_markup=menu_missao_acoes(pedido_id)
    )


@dp.message(F.chat.type == "private", F.document)
async def receber_arquivo(message: Message):
    if not autorizado(message.from_user.id):
        return

    admin_id = message.from_user.id
    pedido_id = pedido_selecionado.get(admin_id)

    if not pedido_id:
        await message.answer("⚠️ Primeiro escolha um pergaminho em 📜 Pergaminhos registrados.")
        return

    arquivos_pendentes.setdefault(admin_id, [])
    arquivos_pendentes[admin_id].append(message.document.file_id)

    total = len(arquivos_pendentes[admin_id])

    await message.answer(
        f"✅ Arquivo recebido.\n"
        f"📦 Total de grimórios preparados neste pergaminho: {total}\n\n"
        "Pode enviar mais PDF/EPUB.\n"
        "Quando terminar, envie a figurinha de confirmação.",
        reply_markup=menu_missao_acoes(pedido_id)
    )


@dp.message(F.chat.type == "private", F.sticker)
async def receber_figurinha(message: Message):
    if not autorizado(message.from_user.id):
        return

    admin_id = message.from_user.id
    chave_edicao = modo_edicao.get(admin_id)

    if chave_edicao == "sticker_nao_encontrei":
        salvar_config("sticker_nao_encontrei", message.sticker.file_id)
        modo_edicao.pop(admin_id, None)

        await message.answer(
            "✅ Figurinha de “não encontrei” salva com sucesso!",
            reply_markup=menu_pv()
        )
        return

    pedido_id = pedido_selecionado.get(admin_id)

    if not pedido_id:
        await message.answer("⚠️ Primeiro escolha um pergaminho em 📜 Pergaminhos registrados.")
        return

    lista_arquivos = arquivos_pendentes.get(admin_id, [])

    if not lista_arquivos:
        await message.answer("⚠️ Envie pelo menos um arquivo antes da figurinha.")
        return

    cursor.execute("""
    SELECT id, nome, pedido, grupo_msg_id, chave_livro, status
    FROM pedidos
    WHERE id = ? AND status IN ('pendente', 'nao_encontrado')
    """, (pedido_id,))
    pedido = cursor.fetchone()

    if not pedido:
        await message.answer("⚠️ Pergaminho não encontrado ou já arquivado.")
        return

    id_pedido, nome, pedido_texto, grupo_msg_id, chave_livro, status = pedido
    numero = numero_visual(id_pedido, status)

    legenda = formatar_mensagem_config(
        "msg_arquivo",
        nome=nome,
        id_pedido=id_pedido,
        numero_missao=numero,
        nome_livro=extrair_nome_livro(pedido_texto)
    )

    for index, arquivo_id in enumerate(lista_arquivos, start=1):
        caption = legenda if index == 1 else None

        await bot.send_document(
            chat_id=GRUPO_ID,
            document=arquivo_id,
            caption=caption,
            reply_to_message_id=grupo_msg_id
        )

    await bot.send_sticker(
        chat_id=GRUPO_ID,
        sticker=message.sticker.file_id,
        reply_to_message_id=grupo_msg_id
    )

    cursor.execute("""
    UPDATE pedidos
    SET status = 'pendente', figurinha_id = ?
    WHERE id = ?
    """, (
        message.sticker.file_id,
        pedido_id
    ))

    conn.commit()

    arquivos_pendentes[admin_id] = []

    await message.answer(
        "✅ Arquivo(s) enviados com sucesso!\n\n"
        "📜 O pergaminho continua aberto.\n"
        "Você pode enviar mais arquivos para esse mesmo pergaminho.\n\n"
        "Quando terminar tudo, toque em ✅ Arquivar pergaminho.",
        reply_markup=menu_missao_acoes(pedido_id)
    )


@dp.callback_query(F.data.startswith("cancelar_envio_"))
async def cancelar_envio(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    admin_id = callback.from_user.id
    pedido_id = int(callback.data.replace("cancelar_envio_", ""))

    arquivos_pendentes[admin_id] = []
    pedido_selecionado[admin_id] = pedido_id

    await callback.message.answer(
        "❌ Envio cancelado.\n\n"
        "Os arquivos preparados foram descartados.\n"
        "O pergaminho continua aberto.\n\n"
        "Agora envie os arquivos corretos novamente.",
        reply_markup=menu_missao_acoes(pedido_id)
    )


@dp.callback_query(F.data.startswith("ja_acervo_"))
async def ja_esta_no_acervo(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    pedido_id = int(callback.data.replace("ja_acervo_", ""))

    cursor.execute("""
    SELECT id, nome, pedido, grupo_msg_id, status
    FROM pedidos
    WHERE id = ? AND status IN ('pendente', 'nao_encontrado')
    """, (pedido_id,))
    pedido = cursor.fetchone()

    if not pedido:
        await callback.message.answer("⚠️ Esse pergaminho não está mais disponível.")
        return

    id_pedido, nome, pedido_texto, grupo_msg_id, status = pedido

    mensagem = formatar_mensagem_config(
        "msg_ja_postado",
        nome=nome,
        id_pedido=id_pedido,
        numero_missao=numero_visual(id_pedido, status),
        nome_livro=extrair_nome_livro(pedido_texto)
    )

    await bot.send_message(
        chat_id=GRUPO_ID,
        text=mensagem,
        reply_to_message_id=grupo_msg_id
    )

    pedido_selecionado[callback.from_user.id] = pedido_id

    await callback.message.answer(
        "🧠 Resposta do Arquivo Inteligente enviada.\n\n"
        "O pergaminho continua aberto até você tocar em ✅ Arquivar pergaminho.",
        reply_markup=menu_missao_acoes(pedido_id)
    )


@dp.callback_query(F.data.startswith("nao_encontrei_"))
async def nao_encontrei(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    pedido_id = int(callback.data.replace("nao_encontrei_", ""))

    cursor.execute("""
    SELECT id, nome, pedido, grupo_msg_id
    FROM pedidos
    WHERE id = ? AND status IN ('pendente', 'nao_encontrado')
    """, (pedido_id,))
    pedido = cursor.fetchone()

    if not pedido:
        await callback.message.answer("⚠️ Esse pergaminho não está mais disponível.")
        return

    id_pedido, nome, pedido_texto, grupo_msg_id = pedido

    mensagem = formatar_mensagem_config(
        "msg_nao_encontrei",
        nome=nome,
        id_pedido=id_pedido,
        numero_missao=numero_visual(id_pedido, "pendente"),
        nome_livro=extrair_nome_livro(pedido_texto)
    )

    await bot.send_message(
        chat_id=GRUPO_ID,
        text=mensagem,
        reply_to_message_id=grupo_msg_id
    )

    sticker_id = pegar_config("sticker_nao_encontrei")

    if sticker_id:
        await bot.send_sticker(
            chat_id=GRUPO_ID,
            sticker=sticker_id,
            reply_to_message_id=grupo_msg_id
        )

    cursor.execute("""
    UPDATE pedidos
    SET status = 'nao_encontrado'
    WHERE id = ?
    """, (pedido_id,))
    conn.commit()

    pedido_selecionado.pop(callback.from_user.id, None)
    arquivos_pendentes.pop(callback.from_user.id, None)

    await callback.message.answer(
        "🔍 Missão enviada para Missões Não Encontradas.\n"
        "Ela saiu da lista principal, mas continua guardada.",
        reply_markup=menu_pv()
    )


@dp.callback_query(F.data.startswith("voltar_pendente_"))
async def voltar_pendente(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    pedido_id = int(callback.data.replace("voltar_pendente_", ""))

    cursor.execute("""
    UPDATE pedidos
    SET status = 'pendente'
    WHERE id = ? AND status = 'nao_encontrado'
    """, (pedido_id,))
    conn.commit()

    await callback.message.answer(
        "📜 Pergaminho voltou para Pergaminhos Registrados.",
        reply_markup=menu_pv()
    )


@dp.callback_query(F.data.startswith("finalizar_"))
async def finalizar_missao(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    admin_id = callback.from_user.id
    pedido_id = int(callback.data.replace("finalizar_", ""))

    cursor.execute("""
    SELECT id, pedido
    FROM pedidos
    WHERE id = ? AND status IN ('pendente', 'nao_encontrado')
    """, (pedido_id,))
    pedido = cursor.fetchone()

    if not pedido:
        await callback.message.answer("⚠️ Esse pergaminho não está mais disponível ou já foi arquivado.")
        return

    _, pedido_texto = pedido
    nome_livro = extrair_nome_livro(pedido_texto)

    # Conta 1 pergaminho arquivado, não a quantidade de arquivos enviados.
    # A chave por pedido permite contar pedidos repetidos sem guardar ficha completa no acervo.
    cursor.execute("""
    INSERT OR IGNORE INTO entregues
    (chave_livro, nome_livro, pedido_id, arquivo_id)
    VALUES (?, ?, ?, ?)
    """, (f"pedido:{pedido_id}", nome_livro, pedido_id, ""))

    cursor.execute("""
    UPDATE pedidos
    SET status = 'concluido'
    WHERE id = ? AND status IN ('pendente', 'nao_encontrado')
    """, (pedido_id,))
    conn.commit()

    pedido_selecionado.pop(admin_id, None)
    arquivos_pendentes.pop(admin_id, None)

    await callback.message.answer(
        "✅ Pergaminho arquivado com sucesso!\n"
        "📜 Ele saiu das listas abertas e entrou no Registro da Biblioteca.",
        reply_markup=menu_pv()
    )


@dp.callback_query(F.data == "personalizar")
async def personalizar(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    await callback.message.answer(
        "✏️ Escolha qual mensagem deseja personalizar:",
        reply_markup=menu_personalizar()
    )


@dp.callback_query(F.data == "arquivo_inteligente")
async def arquivo_inteligente(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    await callback.message.answer(
        "🧠 Arquivo Inteligente\n\n"
        "Aqui você personaliza a resposta manual para pergaminhos que já existem no acervo.",
        reply_markup=menu_arquivo_inteligente()
    )


@dp.callback_query(F.data == "contadores")
async def contadores(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    await callback.message.answer(
        contadores_texto(),
        reply_markup=menu_pv()
    )


@dp.callback_query(F.data == "editar_msg_pedido")
async def editar_msg_pedido(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()
    modo_edicao[callback.from_user.id] = "msg_pedido"

    atual = pegar_config("msg_pedido")

    await callback.message.answer(
        "📜 Envie agora a nova mensagem automática do pergaminho.\n\n"
        f"Mensagem atual:\n\n{atual}"
    )


@dp.callback_query(F.data == "editar_msg_arquivo")
async def editar_msg_arquivo(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()
    modo_edicao[callback.from_user.id] = "msg_arquivo"

    atual = pegar_config("msg_arquivo")

    await callback.message.answer(
        "🎯 Envie agora a nova legenda dos arquivos.\n\n"
        "Você pode usar:\n"
        "{nome} = nome da pessoa\n"
        "{id_pedido} = número interno do pergaminho\n"
        "{numero_missao} = número visual do pergaminho\n"
        "{nome_livro} = nome do livro\n\n"
        f"Mensagem atual:\n\n{atual}"
    )


@dp.callback_query(F.data == "editar_msg_nao_encontrei")
async def editar_msg_nao_encontrei(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()
    modo_edicao[callback.from_user.id] = "msg_nao_encontrei"

    atual = pegar_config("msg_nao_encontrei")

    await callback.message.answer(
        "🔎 Envie agora a nova mensagem de “não encontrei o livro”.\n\n"
        "Você pode usar:\n"
        "{nome} = nome da pessoa\n"
        "{id_pedido} = número interno do pergaminho\n"
        "{numero_missao} = número visual do pergaminho\n"
        "{nome_livro} = nome do livro\n\n"
        f"Mensagem atual:\n\n{atual}"
    )


@dp.callback_query(F.data == "editar_msg_ja_postado")
async def editar_msg_ja_postado(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()
    modo_edicao[callback.from_user.id] = "msg_ja_postado"

    atual = pegar_config("msg_ja_postado")

    await callback.message.answer(
        "✅ Envie agora a nova mensagem do Arquivo Inteligente.\n\n"
        "Essa mensagem será enviada pelo botão 🧠 Já está no acervo.\n\n"
        "Você pode usar:\n"
        "{nome} = nome da pessoa\n"
        "{nome_livro} = nome do livro\n\n"
        f"Mensagem atual:\n\n{atual}"
    )


@dp.callback_query(F.data == "editar_sticker_nao_encontrei")
async def editar_sticker_nao_encontrei(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()
    modo_edicao[callback.from_user.id] = "sticker_nao_encontrei"

    await callback.message.answer(
        "🖼️ Envie agora a figurinha usada em “não encontrei o livro”."
    )


@dp.callback_query(F.data == "voltar_menu")
async def voltar_menu(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    await callback.message.answer(
        "📚 Menu dos Arquivos de Hogwarts:",
        reply_markup=menu_pv()
    )


@dp.callback_query(F.data == "limpar")
async def limpar(callback: CallbackQuery):
    if not autorizado(callback.from_user.id):
        await callback.answer("Sem permissão.", show_alert=True)
        return

    await callback.answer()

    cursor.execute("SELECT COUNT(*) FROM pedidos WHERE status = 'concluido'")
    total = cursor.fetchone()[0]

    if total == 0:
        await callback.message.answer("✅ Não há pergaminhos concluídos para limpar.")
        return

    cursor.execute("DELETE FROM pedidos WHERE status = 'concluido'")
    conn.commit()

    await callback.message.answer(
        f"🧹 {total} pergaminho(s) concluído(s) foram apagados.",
        reply_markup=menu_pv()
    )


async def set_commands():
    commands = [
        BotCommand(command="start", description="Abrir painel da Guardiã"),
        BotCommand(command="menu", description="Abrir menu principal"),
    ]
    await bot.set_my_commands(commands)


async def main():
    print("Bot Guardiã dos Livros iniciado...")
    await set_commands()
    # Não processa mensagens antigas quando reiniciar na plataforma 24h.
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
