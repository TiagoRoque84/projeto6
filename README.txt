Como aplicar (HOME com novos cards):
1) Faça backup de:
   - templates/index.html
   - blueprints/main/routes.py
2) Extraia este ZIP na raiz do projeto e confirme a substituição.
3) Reinicie o servidor (python app.py) e abra http://127.0.0.1:5000/

Observação: se seu Employee usa outro campo para CNH (ex.: cnh_validade),
ajuste a seleção no blueprints/main/routes.py em 'cart_expired/cart_expiring'.
