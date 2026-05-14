import os
import sys
import discord
from discord.ext import commands
import requests
from typing import Optional
import asyncio
import logging
from pathlib import Path
from dotenv import load_dotenv

# ============= CARGAR .ENV =============
env_path = Path(__file__).parent / '.env'

if env_path.exists():
    load_dotenv(env_path)
    print(f"✅ .env cargado desde: {env_path}")
else:
    print(f"⚠️  .env no encontrado, usando variables de entorno del sistema")

# ============= LOGGING =============
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============= CONFIGURACIÓN =============
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
HOOK_TOKEN = os.getenv('HOOK_TOKEN')
PUBLIC_BASE = os.getenv('PUBLIC_BASE')

# ✅ VALIDACIÓN CRÍTICA
logger.info("=" * 80)
logger.info("🔍 VERIFICANDO CONFIGURACIÓN")
logger.info("=" * 80)

logger.debug(f"Buscando .env en: {env_path}")
logger.debug(f"Existe: {env_path.exists()}")

if not DISCORD_BOT_TOKEN:
    logger.error("❌ DISCORD_BOT_TOKEN NO CONFIGURADO")
    logger.error("   Configura en .env: DISCORD_BOT_TOKEN=tu_token")
    sys.exit(1)

if not HOOK_TOKEN:
    logger.error("❌ HOOK_TOKEN NO CONFIGURADO")
    logger.error("   Configura en .env: HOOK_TOKEN=tu_token")
    sys.exit(1)

if not PUBLIC_BASE:
    logger.error("❌ PUBLIC_BASE NO CONFIGURADO")
    logger.error("   Configura en .env: PUBLIC_BASE=https://tu-app.com")
    sys.exit(1)

logger.info("✅ DISCORD_BOT_TOKEN: Configurado")
logger.info(f"✅ HOOK_TOKEN: {HOOK_TOKEN[:15]}...***")
logger.info(f"✅ PUBLIC_BASE: {PUBLIC_BASE}")

# Verificar conectividad al servidor
logger.info(f"🔍 Verificando conectividad a {PUBLIC_BASE}...")
try:
    health = requests.get(f"{PUBLIC_BASE}/health", timeout=5)
    logger.info(f"✅ Servidor {PUBLIC_BASE} está activo (Status: {health.status_code})")
except Exception as e:
    logger.warning(f"⚠️  No se puede conectar a {PUBLIC_BASE}: {e}")
    logger.warning("   El servidor debe estar activo para que funcione el bot")

logger.info("=" * 80)

# ============= INTENTS =============
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='/', intents=intents)

# ============= EVENTOS =============
@bot.event
async def on_ready():
    """Se ejecuta cuando el bot se conecta"""
    logger.info("=" * 80)
    logger.info("✅ BOT CONECTADO")
    logger.info(f"🤖 Usuario: {bot.user}")
    logger.info(f"📍 Servidores: {len(bot.guilds)}")
    logger.info("=" * 80)
    
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ {len(synced)} comando(s) sincronizado(s)")
    except Exception as e:
        logger.error(f"❌ Error sincronizando comandos: {e}", exc_info=True)
    
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="links tracked 🔗"
        )
    )

# ============= FUNCIONES AUXILIARES =============

def validar_url(url: str) -> bool:
    """Valida que la URL sea correcta"""
    if not url:
        return False
    return url.startswith(('http://', 'https://'))

def hacer_request(payload: dict) -> Optional[dict]:
    """Realiza request al servidor de tracking"""
    try:
        convert_url = f"{PUBLIC_BASE}/convert"
        headers = {"x-hook-token": HOOK_TOKEN}
        
        logger.info(f"📤 Enviando POST a {convert_url}")
        logger.debug(f"   Payload: {payload}")
        logger.debug(f"   Headers: {headers}")
        
        response = requests.post(
            convert_url,
            json=payload,
            headers=headers,
            timeout=15
        )
        
        logger.info(f"📥 Respuesta: Status {response.status_code}")
        logger.debug(f"   Body: {response.text[:500]}")
        
        if response.ok:
            try:
                data = response.json()
                logger.info(f"✅ JSON válido recibido")
                logger.debug(f"   Datos: {data}")
                return data
            except Exception as e:
                logger.error(f"❌ Error parseando JSON: {e}")
                logger.error(f"   Response: {response.text}")
                return {"error": f"JSON inválido: {e}"}
        else:
            error_msg = f"Status {response.status_code}: {response.text[:200]}"
            logger.error(f"❌ {error_msg}")
            return {"error": error_msg}
    
    except requests.exceptions.Timeout:
        logger.error("❌ Timeout - El servidor tardó más de 15 segundos en responder")
        return {"error": "Timeout - Servidor no responde"}
    
    except requests.exceptions.ConnectionError as e:
        logger.error(f"❌ No se pudo conectar a {PUBLIC_BASE}")
        logger.error(f"   Error: {e}")
        return {"error": f"No se pudo conectar a {PUBLIC_BASE}"}
    
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}", exc_info=True)
        return {"error": str(e)}

# ============= COMANDOS =============

@bot.tree.command(name="track", description="Crear un link que captura IP")
async def track(
    interaction: discord.Interaction,
    url: str,
    name: Optional[str] = None
):
    """Crea un link tracked"""
    await interaction.response.defer(ephemeral=True)
    
    logger.info("=" * 80)
    logger.info(f"📝 Comando /track ejecutado")
    logger.info(f"   Usuario: {interaction.user}")
    logger.info(f"   URL: {url}")
    logger.info(f"   Nombre: {name}")
    logger.info("=" * 80)
    
    if not validar_url(url):
        logger.warning(f"❌ URL inválida: {url}")
        await interaction.followup.send(
            "❌ URL inválida\nDebe empezar con `http://` o `https://`",
            ephemeral=True
        )
        return
    
    try:
        # Preparar payload
        payload = {"url": url}
        if name and name.strip():
            payload["name"] = name.strip()
        
        logger.info("📤 Haciendo request al servidor...")
        data = await asyncio.to_thread(hacer_request, payload)
        
        logger.info(f"📊 Respuesta del servidor:")
        logger.info(f"   {data}")
        
        # Validar respuesta
        if not data:
            logger.error("❌ Respuesta vacía del servidor")
            await interaction.followup.send(
                "❌ El servidor no devolvió datos",
                ephemeral=True
            )
            return
        
        if "error" in data:
            error = data.get("error", "Error desconocido")
            logger.error(f"❌ Error del servidor: {error}")
            await interaction.followup.send(
                f"❌ Error: {error}",
                ephemeral=True
            )
            return
        
        # =====================================================================
        # SOLUCIÓN: Construir el link original con #slug al final
        # =====================================================================
        
        # Extraer el slug
        slug = data.get('slug') or data.get('tracker_id') or data.get('id')
        
        if not slug:
            logger.error(f"❌ No se encontró slug en la respuesta: {data}")
            await interaction.followup.send(
                "❌ Error: No se pudo generar el tracker ID",
                ephemeral=True
            )
            return
        
        # AQUÍ ES LA CLAVE: Construir tracked_url como URL original + #slug
        # Esto mantiene la URL original visible pero agrega el tracker invisible
        tracked_url = f"{url}#{slug}"
        
        short_url = data.get('short_url')
        if short_url and not short_url.startswith('http'):
            short_url = f"{PUBLIC_BASE}{short_url}"
        
        logger.info(f"✅ Campos construidos:")
        logger.info(f"   URL Original: {url}")
        logger.info(f"   Slug: {slug}")
        logger.info(f"   Tracked URL: {tracked_url}")
        logger.info(f"   Short URL: {short_url}")
        
        # =====================================================================
        
        tipo = data.get('tipo', 'enlace')
        
        # Crear embed
        embed = discord.Embed(
            title="✅ Link Tracker Creado 🔗",
            description="La URL se ve exactamente como el original",
            color=discord.Color.green()
        )
        
        # LINK PRINCIPAL A COMPARTIR (con #slug invisible)
        embed.add_field(
            name="🔗 LINK PARA COMPARTIR (Con Tracker Invisible)",
            value=f"`{tracked_url}`",
            inline=False
        )
        
        embed.add_field(
            name="📋 Copiar",
            value=f"```\n{tracked_url}\n```",
            inline=False
        )
        
        # Si hay short URL, mostrarla como alternativa
        if short_url:
            embed.add_field(
                name="📏 Link Corto (Alternativa)",
                value=f"`{short_url}`",
                inline=False
            )
        
        embed.add_field(
            name="📊 ID Tracking",
            value=f"`{slug}`",
            inline=True
        )
        
        embed.add_field(
            name="📝 Tipo",
            value=f"`{tipo}`",
            inline=True
        )
        
        embed.add_field(
            name="🎯 URL Original",
            value=f"`{url[:70]}...`" if len(url) > 70 else f"`{url}`",
            inline=False
        )
        
        if name and name.strip():
            embed.add_field(name="📛 Nombre", value=f"`{name.strip()}`", inline=True)
        
        embed.add_field(
            name="📈 Ver Estadísticas",
            value=f"Usa `/stats {slug}`",
            inline=False
        )
        
        embed.set_footer(text="✨ El #slug es invisible en navegadores")
        embed.timestamp = discord.utils.utcnow()
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"✅ Link creado exitosamente")
        logger.info("=" * 80)
    
    except Exception as e:
        logger.error(f"❌ Error en /track: {e}", exc_info=True)
        await interaction.followup.send(
            f"❌ Error: {str(e)[:100]}",
            ephemeral=True
        )

@bot.tree.command(name="stats", description="Ver estadísticas")
async def stats(interaction: discord.Interaction, tracker_id: str):
    """Ver estadísticas del link"""
    await interaction.response.defer(ephemeral=True)
    
    logger.info(f"📊 Stats solicitadas para ID: {tracker_id}")
    
    try:
        stats_url = f"{PUBLIC_BASE}/stats/{tracker_id}"
        logger.debug(f"   GET {stats_url}")
        
        response = requests.get(stats_url, timeout=10)
        
        if not response.ok:
            logger.warning(f"❌ Link no encontrado: {tracker_id}")
            await interaction.followup.send(
                f"❌ Link no encontrado: `{tracker_id}`",
                ephemeral=True
            )
            return
        
        data = response.json()
        
        embed = discord.Embed(
            title="📊 Estadísticas 🔗",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🔗 URL Original",
            value=f"`{data.get('url', 'N/A')}`",
            inline=False
        )
        
        embed.add_field(
            name="👁️ Vistas",
            value=f"`{data.get('hits', 0)}`",
            inline=True
        )
        
        embed.add_field(
            name="📅 Creado",
            value=f"`{data.get('created_at', 'N/A')}`",
            inline=True
        )
        
        if data.get('name'):
            embed.add_field(name="📛 Nombre", value=f"`{data['name']}`", inline=True)
        
        embed.set_footer(text=f"ID: {tracker_id}")
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        logger.info(f"✅ Stats mostradas")
    
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        await interaction.followup.send(
            f"❌ Error: {str(e)[:100]}",
            ephemeral=True
        )

@bot.tree.command(name="info", description="Info del bot")
async def info(interaction: discord.Interaction):
    """Muestra información del bot"""
    embed = discord.Embed(
        title="🎯 Bot Tracker",
        description="Links que capturan IP sin dejar rastro",
        color=discord.Color.blue()
    )
    embed.add_field(name="📍 Base URL", value=f"`{PUBLIC_BASE}`", inline=False)
    embed.add_field(name="✨ Estado", value="`✅ Activo`", inline=True)
    embed.add_field(name="📍 Servidores", value=f"`{len(bot.guilds)}`", inline=True)
    embed.set_footer(text="Usa /track para crear un link")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============= MAIN =============

if __name__ == "__main__":
    logger.info("🚀 INICIANDO BOT TRACKER")
    logger.info("=" * 80)
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except discord.errors.LoginFailure:
        logger.error("❌ TOKEN INVÁLIDO O EXPIRADO")
        logger.error("   Regenera el token en: https://discord.com/developers/applications")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("⏹️  Bot detenido por el usuario")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}", exc_info=True)
        sys.exit(1)
