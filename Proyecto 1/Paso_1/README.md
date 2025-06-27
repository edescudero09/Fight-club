# 🔌 Simulación de Campo Eléctrico de un Dipolo

Este proyecto tuvo como objetivo visualizar el campo eléctrico generado por un dipolo eléctrico, utilizando Python y las librerías `numpy` y `matplotlib`. Se exploran tanto representaciones en 2D como en 3D, abordando los desafíos numéricos y visuales que surgen al simular este tipo de sistemas.

---

## 🎯 Objetivos

- Comprender y aplicar conceptos de campo eléctrico y dipolos.
- Implementar funciones para calcular el campo eléctrico de cargas puntuales.
- Visualizar líneas de campo eléctrico en 2D y vectores de campo en 3D.
- Resolver errores comunes en simulaciones numéricas (singularidades, dimensiones, etc.).

---

## 🧠 Fundamento Teórico

El campo eléctrico de una carga puntual se calcula mediante:

\[
\vec{E} = k \cdot \frac{q (\vec{r} - \vec{r}_0)}{|\vec{r} - \vec{r}_0|^3}
\]

Donde:
- \( q \) es la carga,
- \( \vec{r}_0 \) es la posición de la carga,
- \( \vec{r} \) es el punto de observación,
- \( k \) es la constante de Coulomb.

Un **dipolo eléctrico** se modela como dos cargas opuestas separadas por una distancia \( d \), y su campo total es la suma vectorial de los campos individuales.

---

## 🧰 Herramientas utilizadas

- **Python 3**
- `numpy` – Cálculo numérico
- `matplotlib` – Visualización 2D y 3D
- `mpl_toolkits.mplot3d` – Gráficos vectoriales en 3D

---

## 📁 Estructura del proyecto

El desarrollo del proyecto se realizó en un entorno Jupyter Notebook, siguiendo un enfoque exploratorio basado en prueba y error. A medida que surgían ideas, se implementaban y evaluaban en tiempo real, permitiendo identificar qué enfoques eran funcionales y cuáles requerían ajustes. Esta metodología favoreció el aprendizaje activo y la mejora progresiva del código y las visualizaciones.

## 🥳 Conclusión

Este proyecto nació como una extensión de un trabajo universitario, con el objetivo de mantener activas mis habilidades de programación y fortalecer mi capacidad para desarrollar proyectos de forma autónoma. Aunque no representa un aporte directo a la ciencia, sí marcó un avance significativo en mi crecimiento como profesional. Me permitió explorar nuevas herramientas, enfrentar desafíos técnicos reales y reafirmar mi interés por la simulación física y la visualización científica.
