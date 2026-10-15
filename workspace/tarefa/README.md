# tarefa — pouso autônomo na base indicada (mundo missao1)

O enunciado completo, o guia do ambiente e as regras de pontuação estão no PDF
`Tarefa_Pouso_Autonomo_missao1.pdf` distribuído com esta tarefa.

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
