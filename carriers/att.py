# carriers/att.py
import asyncio
import logging
import os
from playwright.async_api import async_playwright, TimeoutError as PwTimeout
from typing import Optional

# Si SLIDER.py es un archivo separado, puedes importarlo. 
# Aquí incluyo la lógica crítica adaptada directamente para evitar conflictos de importación en Railway.

logger = logging.getLogger(__name__)

# Constantes de SLIDER.py
ATT_ORIGIN = "https://www.att.com.mx"
ATT_PORTAL_URL = f"{ATT_ORIGIN}/vinculatulinearegistro/"

_SOLVE_SLIDER_JS = """
(() => {
 const r = document.querySelector('#myRange');
 if (!r) return 'no-slider';
 const target = window.__captchaTarget;
 if (target == null) return 'no-target';

 const val = String(target);
 const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
 const fire = (type, extra) => {
 try { r.dispatchEvent(new Event(type, { bubbles: true, cancelable: true, ...(extra || {}) })); } catch (e) {}
 };
 const firePointer = (type) => {
 try { r.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, pointerId: 1, pointerType: 'touch', isPrimary: true, clientX: 200, clientY: 400 })); } catch (e) {}
 };
 const fireMouse = (type) => {
 try { r.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: 200, clientY: 400 })); } catch (e) {}
 };
 const fireTouch = (type) => {
 try { const t = new Touch({ identifier: 1, target: r, clientX: 200, clientY: 400 }); r.dispatchEvent(new TouchEvent(type, { bubbles: true, cancelable: true, touches: type === 'touchend' ? [] : [t], targetTouches: type === 'touchend' ? [] : [t], changedTouches: [t] })); } catch (e) {}
 };

 firePointer('pointerdown'); fireMouse('mousedown'); fireTouch('touchstart');
 const min = Number(r.min || 0); const max = Number(r.max || 100); const goal = Number(val);
 const steps = 6;
 for (let i = 1; i <= steps; i++) { const v = Math.round(min + ((goal - min) * i) / steps); setter.call(r, String(v)); fire('input'); firePointer('pointermove'); fireMouse('mousemove'); }
 setter.call(r, val); fire('input'); fire('change'); firePointer('pointerup'); fireMouse('mouseup'); fireTouch('touchend');
 try { if (window.jQuery) { window.jQuery(r).val(val).trigger('input').trigger('change').trigger('mouseup'); } } catch (e) {}
 const btn = document.querySelector('#btnVerify, #verify, .btn-verify, button.verify, button[onclick*="verif"], button[onclick*="check"]');
 if (btn) { try { btn.click(); } catch (e) {} }
 const form = r.closest('form');
 if (form) { try { form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); } catch (e) {} }
 return 'solved:' + val;
})();
"""

class ATTDriver:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None

    async def start(self):
        self.browser = await async_playwright().start()
        # Usar Chromium con headless mode para Railway
        self.browser_instance = await self.browser.chromium.launch(headless=True)
        self.context = await self.browser_instance.new_context(
            viewport={"width": 412, "height": 915},
            is_mobile=True,
            has_touch=True,
            user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Mobile Safari/537.36"
        )
        self.page = await self.context.new_page()
        await self.page.goto(ATT_PORTAL_URL, wait_until="domcontentloaded")

    async def solve_slider(self):
        # Inyectar detector de dígitos
        await self.page.evaluate("""
            (() => {
                try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch (e) {}
                const orig = CanvasRenderingContext2D.prototype.fillText;
                CanvasRenderingContext2D.prototype.fillText = function (t) {
                    const s = String(t);
                    if (/^\\d{1,2}$/.test(s)) {
                        const now = Date.now();
                        if (window.__captchaTargetTs && (now - window.__captchaTargetTs) < 80 && /^\\d$/.test(String(window.__captchaTarget || '')) && /^\\d$/.test(s)) {
                            window.__captchaTarget = String(window.__captchaTarget) + s;
                        } else {
                            window.__captchaTarget = s;
                        }
                        window.__captchaTargetTs = now;
                    }
                    return orig.apply(this, arguments);
                };
            })()
        """)

        # Esperar a que aparezca el slider
        try:
            await self.page.wait_for_selector("#myRange", timeout=15000)
        except:
            raise Exception("No se encontró el slider de AT&T")

        # Obtener objetivo
        target = await self.page.evaluate("() => window.__captchaTarget")
        if not target:
            raise Exception("No se pudo detectar el número objetivo del slider")

        # Ejecutar solución
        result = await self.page.evaluate(_SOLVE_SLIDER_JS)
        logger.info(f"Slider resuelto: {result}")
        
        # Verificar valor final
        current_val = await self.page.evaluate("() => document.querySelector('#myRange')?.value")
        if str(current_val) != str(target):
            # Reintentar con setter directo
            await self.page.evaluate(f"""
                (() => {{
                    const r = document.querySelector('#myRange');
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(r, "{target}");
                    r.dispatchEvent(new Event('input', {{bubbles: true}}));
                    r.dispatchEvent(new Event('change', {{bubbles: true}}));
                }})()
            """)

    async def fill_profile(self, profile_data):
        """Rellena los campos básicos con los datos del perfil"""
        # Esto depende del HTML específico de AT&T. 
        # Basado en la estructura común de estos portales:
        
        # Intentar encontrar inputs por placeholder o name
        # Nota: Como AT&T usa React, los selectores pueden ser dinámicos. 
        # Usaremos selects genéricos basados en atributos comunes.
        
        inputs = await self.page.locator("input").all()
        for inp in inputs:
            placeholder = await inp.get_attribute("placeholder") or ""
            name = await inp.get_attribute("name") or ""
            
            if "nombre" in placeholder.lower() or "nombre" in name.lower():
                await inp.fill(profile_data['full_name'])
            elif "curp" in placeholder.lower() or "curp" in name.lower():
                # Necesitaríamos extraer CURP del INE, por ahora dejamos vacío o simulado
                pass
            elif "telefono" in placeholder.lower() or "msisdn" in name.lower():
                await inp.fill(profile_data.get('phone', ''))

    async def upload_images(self, profile_data):
        """Sube las imágenes. Playwright permite subir archivos locales."""
        # Selector típico para input file
        file_input = await self.page.locator("input[type='file']").first
        
        # Subir frente
        if profile_data.get('ine_front'):
            # Asumimos que profile_data tiene rutas absolutas o relativas al working dir
            path = profile_data['ine_front']
            await file_input.set_input_files(path)
            await self.page.wait_for_timeout(1000) # Esperar carga UI

        # Subir reverso
        # Normalmente hay dos inputs file o uno que cambia. 
        # Si es el mismo input, necesitamos clickear otro botón o usar JS.
        # Para AT&T, usualmente son dos zonas de drop.
        
        # Estrategia robusta: Buscar todos los inputs file y asignar secuencialmente
        all_file_inputs = await self.page.locator("input[type='file']").all()
        
        files_to_upload = [profile_data.get('ine_front'), profile_data.get('ine_back')]
        
        for i, file_path in enumerate(files_to_upload):
            if i < len(all_file_inputs) and file_path:
                try:
                    await all_file_inputs[i].set_input_files(file_path)
                    await self.page.wait_for_timeout(1000)
                except Exception as e:
                    logger.warning(f"Fallo subiendo archivo {i}: {e}")

    async def take_selfie(self, profile_data):
        """Simula la selfie o sube la imagen de selfie si el portal lo permite."""
        # Muchos portales usan cámara nativa. Para automatización, usamos la imagen guardada.
        if profile_data.get('selfie_url'):
            # Intentar encontrar el segundo input file o el específico de selfie
            all_file_inputs = await self.page.locator("input[type='file']").all()
            if len(all_file_inputs) > 2:
                await all_file_inputs[2].set_input_files(profile_data['selfie_url'])
            else:
                # Fallback: Si solo hay 2 inputs, quizás la selfie va en el segundo o primero tras un click
                # O el portal pide hacer click en "Tomar foto" y luego sube.
                # Simulamos clic en botón de cámara si existe
                camera_btn = await self.page.locator("button:has-text('camera'), button:has-text('tomar foto'), i.fa-camera").first
                if await camera_btn.count():
                    await camera_btn.click()
                    await self.page.wait_for_timeout(2000)
                    # Después de abrir cámara, suele aparecer un input file oculto o modal
                    # Reintentamos buscar inputs file
                    updated_inputs = await self.page.locator("input[type='file']").all()
                    if len(updated_inputs) > 2:
                         await updated_inputs[2].set_input_files(profile_data['selfie_url'])

    async def complete(self):
        """Click en botón de finalizar/vincular"""
        submit_btn = await self.page.locator("button:has-text('Enviar'), button:has-text('Vincular'), button:has-text('Continuar')").first
        if await submit_btn.count():
            await submit_btn.click()
            await self.page.wait_for_load_state("networkidle")
            return True
        return False

    async def close(self):
        if self.context:
            await self.context.close()
        if self.browser_instance:
            await self.browser_instance.close()
