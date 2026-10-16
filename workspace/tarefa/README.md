# tarefa — pouso autônomo na base indicada (mundo missao1)

A tarefa vem em dois PDFs distribuídos junto com esta pasta:

- `Tarefa_Enunciado_missao1.pdf` — o problema, o mundo missao1, os requisitos e as regras de pontuação;
- `Tarefa_Documentacao_missao1.pdf` — o ambiente de simulação, o guia passo a passo, a interface do
  kit e o resumo da uav-api.

- `kit/` — arquivos fornecidos: `vision.py` (detecção/identificação de bases), `take_photo.py`
  (última foto da câmera), `avaliador.py` (pontuação automática) e o template `missao.py`.
  Não edite o kit.
- `solucao/<seu_nome>/` — sua cópia do kit, onde você implementa `missao()` em `missao.py`.

No container, com a simulação no ar (`start_simulation.sh missao1`):

```bash
cp -r ~/workspace/tarefa/kit ~/workspace/tarefa/solucao/<seu_nome>
code ~/workspace/tarefa/solucao/<seu_nome>
cd ~/workspace/tarefa/solucao/<seu_nome> && python3 missao.py --forma Hexagono --numero 5
```

Cada execução imprime a pontuação no console e acrescenta uma linha em `resultados.csv`
na pasta da solução. Essa pasta é a `workspace/tarefa/solucao/<seu_nome>/` do clone no host:
ela sobrevive ao fechamento do container.
