"""Views for the game app."""

from django.contrib import messages as msg
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View

from game.models import Game
from helpers import group_send_sync, make_game


class LeaveGame(LoginRequiredMixin, View):
    """View for leaving a game."""
    def post(self, request):
        """Leave a game."""
        player = request.user.player
        game = player.game
        message, next_ = "You left the game successfully", "/play/"
        if not game:
            message = "Error occured (NIG)"
        elif game.ongoing:
            message = "You need to stay in the game till it ends."
        elif player.creator and game.joined > 1:
            message = "You can only leave if no one else has joined, start early instead."
        else:
            message = "Sorry you could not wait! Make a game/join one below."
            player.reset(end=player.creator)
            next_ = "/lounge/"
            # Tell other players.
            group_send_sync(group_name=game.id, data={
                "handler": "playerLeave", "data": request.user.username})

        msg.add_message(request, msg.ERROR, message)
        return redirect(next_)

class StartEarly(LoginRequiredMixin, View):
    """View for starting a game early."""
    def post(self, request):
        """Start a game early."""
        player = request.user.player
        game = player.game
        if not game or game.ongoing or game.no_of_players < 2:
            msg.add_message(request, msg.ERROR, "Cannot perform that action.")
            return redirect("/lounge/")
        game.no_of_players = game.joined
        game.save()
        msg.add_message(request, msg.SUCCESS, "Game will start soon.")
        return redirect("/play/")

@login_required
def play(request):
    """View for playing a game."""
    player = request.user.player
    game = player.game
    error_msg = (not game) * "You are not in a game.\n"
    error_msg = error_msg or (game.ended) * "You can no longer join that game."
    if error_msg:  # Can't join
        player.game = None
        player.save()
        msg.add_message(request, msg.ERROR, error_msg)
        return redirect("/lounge/")
    # Render game, socket and Consumers will create game and 
    # send data to all users so that JS can build it
    # It will send their positions to them too.
    # But first, let me do the waiting for them that will first trigger
    # Game.start()
    if not (player.joined and player.present):
        player.joined = player.present = True
        player.save()
    context = {
        "multiplayer": True,
        "players": {player.user.username: [
            player.joined, player.present] for player in game.players},
        "game": game,
        "game_data": game.try_start()
    }
    return render(request, "app/game.html", context)

class JoinGame(LoginRequiredMixin, View):
    """View for joining a game."""
    def post(self, request):
        """Join a game."""
        player = request.user.player
        if player.game:
            msg.add_message(request, msg.WARNING, "You are already in a game")
            return redirect("/play/")
        try:
            game_id = int(request.POST["game_id"])
            game = Game.objects.get(id=game_id)
            if game.available:
                player.game = game
                player.save()
                msg.add_message(request, msg.SUCCESS, "You joined the game successfully")
                # Send the "Gamer's" username, with event "createGamer"
                # Channel to all (Message will create an object on all player's platforms with joined=false, present=false)
                group_send_sync(group_name=game_id, data={
                    "handler": "createGamer", "data": request.user.username})
        except:
            msg.add_message(request, msg.ERROR
                            , "An error occured so you could not join the game")
        return redirect("/play/")

class EndGame(LoginRequiredMixin, View):
    """View for ending a game."""
    def post(self, request):
        """End a game."""
        won = +("won" in request.POST)
        request.user.player.reset(won)
        msg.add_message(request, msg.SUCCESS
            , ["Sorry about losing that game. Do better next time."
            , "Congrats on winning that game! You've ranked up."][won])
        return redirect("/lounge/")

# @login_required
def practice(request):
    """View for practicing a game."""
    return render(request, "app/game.html", {"game_data": make_game(10)})
